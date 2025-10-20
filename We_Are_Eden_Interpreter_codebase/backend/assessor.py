#!/usr/bin/env python3

import asyncio
import json
import os
from typing import List, Dict, Any, AsyncGenerator
import boto3
from strands import Agent
from strands.models import BedrockModel
from strands.types.content import ContentBlock

from backend.models import ComparisonResult, PolicyAssessmentResult, Recommendation
from backend.loader import DocumentLoader


class PolicyAssessor:
    """Main class for assessing policies against reference documents."""
    
    def __init__(self, categories_file: str = "config/document_categories.json"):
        """
        Initialize the policy assessor.
        
        Args:
            categories_file: Path to the document categories JSON file
        """
        self.categories_file = categories_file
        self.document_categories = self._load_categories()
    
    def _load_categories(self) -> Dict[str, Any]:
        """Load document categories from JSON file."""
        with open(self.categories_file, "r") as file:
            return json.load(file)
    
    @staticmethod
    def _create_agent() -> Agent:
        """Create a fresh Strands Agent with Bedrock model for each comparison."""
        # Use default credential chain (env vars, profiles, IAM roles, etc.)
        session = boto3.Session(region_name=os.getenv('AWS_REGION', 'us-east-1'))
        
        return Agent(
            model=BedrockModel(
                model_id='us.anthropic.claude-sonnet-4-20250514-v1:0',
                boto_session=session,
                # Enable 1M token context window
                additional_request_fields={
                    "anthropic_beta": ["context-1m-2025-08-07"]
                }
            ),
            system_prompt="""You are an expert legal and policy analyst specializing in employment law. 
            You have deep knowledge of UK employment legislation, workplace policies, and compliance requirements.
            
            When comparing documents, you must:
            1. Identify gaps, inconsistencies, and compliance issues
            2. Provide exactly 3 actionable recommendations
            3. Prioritize recommendations by risk level (HIGH/MEDIUM/LOW)
            4. Include specific citations and implementation guidance
            5. Be thorough but concise in your analysis
            6. Max 40 words per recommendation
            
            Focus on practical, implementable solutions that address real compliance and policy gaps."""
        )
    
    async def assess_policy(self, policy_path: str, category: str) -> PolicyAssessmentResult:
        """
        Assess a policy document against all reference documents in the specified category.
        
        Args:
            policy_path: Path to the policy document to assess
            category: Category of the policy (maternity, fertility, menopause, breastfeeding)
            
        Returns:
            PolicyAssessmentResult containing all comparisons and recommendations
        """
        if category not in self.document_categories:
            raise ValueError(f"Unknown category: {category}")
        
        # Load policy document
        policy_bytes, policy_media_type = DocumentLoader.load_document(policy_path)
        policy_name = DocumentLoader.get_document_name(policy_path)
        
        print(f"Assessing policy: {policy_name}")
        print(f"Category: {category}")
        print(f"Policy size: {len(policy_bytes)} bytes")
        
        # Get all reference documents for this category
        all_reference_docs = []
        category_data = self.document_categories[category]
        
        for doc_type in ["legislation", "guidelines", "news"]:
            if doc_type in category_data:
                for doc_path in category_data[doc_type]:
                    all_reference_docs.append((doc_path, doc_type))
        
        print(f"Found {len(all_reference_docs)} reference documents to compare against")
        
        # Process each reference document
        comparison_results = []
        for i, (ref_doc_path, doc_type) in enumerate(all_reference_docs, 1):
            print(f"\nProcessing document {i}/{len(all_reference_docs)}: {ref_doc_path}")
            
            try:
                result = await self._compare_documents(
                    policy_bytes, policy_media_type, policy_name,
                    ref_doc_path, doc_type
                )
                comparison_results.append(result)
                print(f"✓ Completed comparison with {result.document_name}")
                
            except Exception as e:
                print(f"✗ Error comparing with {ref_doc_path}: {e}")
                continue
        
        # Create final assessment result
        assessment_result = PolicyAssessmentResult.create(
            policy_name=policy_name,
            policy_path=policy_path,
            category=category,
            results=comparison_results
        )
        
        print(f"\nAssessment completed!")
        print(f"Total documents compared: {assessment_result.total_documents_compared}")
        print(f"Total recommendations generated: {assessment_result.total_recommendations}")
        
        return assessment_result
    
    async def assess_policy_with_progress(
        self, policy_path: str, category: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Assess a policy document with progress updates via SSE events.
        
        Args:
            policy_path: Path to the policy document to assess
            category: Category of the policy (maternity, fertility, menopause, breastfeeding)
            
        Yields:
            Progress events as dictionaries
        """
        if category not in self.document_categories:
            raise ValueError(f"Unknown category: {category}")
        
        # Load policy document
        policy_bytes, policy_media_type = DocumentLoader.load_document(policy_path)
        policy_name = DocumentLoader.get_document_name(policy_path)
        
        # Get all reference documents for this category
        all_reference_docs = []
        category_data = self.document_categories[category]
        
        for doc_type in ["legislation", "guidelines", "news"]:
            if doc_type in category_data:
                for doc_path in category_data[doc_type]:
                    all_reference_docs.append((doc_path, doc_type))
        
        # Emit start event
        yield {
            "type": "start",
            "policy_name": policy_name,
            "category": category,
            "total_documents": len(all_reference_docs)
        }
        
        # Process each reference document with progress updates
        comparison_results = []
        for i, (ref_doc_path, doc_type) in enumerate(all_reference_docs, 1):
            ref_name = DocumentLoader.get_document_name(ref_doc_path)
            
            # Emit progress event
            yield {
                "type": "progress",
                "current_document": i,
                "total_documents": len(all_reference_docs),
                "document_name": ref_name,
                "document_type": doc_type,
                "message": f"Comparing against {ref_name}..."
            }
            
            try:
                result = await self._compare_documents(
                    policy_bytes, policy_media_type, policy_name,
                    ref_doc_path, doc_type
                )
                comparison_results.append(result)
                
                # Emit completion for this document
                yield {
                    "type": "document_complete",
                    "current_document": i,
                    "document_name": ref_name,
                    "recommendations_count": len(result.recommendations)
                }
                
            except Exception as e:
                # Emit error for this document but continue
                yield {
                    "type": "document_error",
                    "current_document": i,
                    "document_name": ref_name,
                    "error": str(e)
                }
                continue
        
        # Create final assessment result
        assessment_result = PolicyAssessmentResult.create(
            policy_name=policy_name,
            policy_path=policy_path,
            category=category,
            results=comparison_results
        )
        
        # Emit completion event with final results
        yield {
            "type": "complete",
            "result": assessment_result.model_dump()
        }
    
    async def _compare_documents(
        self, 
        policy_bytes: bytes, 
        policy_media_type: str,
        policy_name: str,
        ref_doc_path: str, 
        doc_type: str
    ) -> ComparisonResult:
        """
        Compare policy document against a single reference document.
        
        Args:
            policy_bytes: Policy document content as bytes
            policy_media_type: Media type of policy document
            policy_name: Name of the policy document
            ref_doc_path: Path to reference document
            doc_type: Type of reference document (legislation/guidelines/news)
            
        Returns:
            ComparisonResult with exactly 3 recommendations
        """
        # Load reference document
        ref_bytes, ref_media_type = DocumentLoader.load_document(ref_doc_path)
        ref_name = DocumentLoader.get_document_name(ref_doc_path)
        
        # Prepare content blocks for Strands Agent
        content_blocks: List[ContentBlock] = [
            {
                "document": {
                    "format": "pdf",  # Policy is always PDF
                    "name": self._sanitize_document_name(f"Policy {policy_name}"),
                    "source": {"bytes": policy_bytes},
                    "citations": {"enabled": True}
                }
            }
        ]
        
        # Handle different document types
        if ref_media_type == "text/plain":
            # For text files, include content as text block
            text_content = ref_bytes.decode('utf-8')
            content_blocks.append({
                "text": f"Reference Document: {ref_name}\n\n{text_content}"
            })
        else:
            # For PDFs and other documents, include as document block
            # Disable citations for DOCX files (not supported by Bedrock)
            is_docx = ref_doc_path.lower().endswith('.docx')
            
            content_blocks.append({
                "document": {
                    "format": ref_doc_path.split('.')[-1].lower(),
                    "name": self._sanitize_document_name(f"Reference {ref_name}"),
                    "source": {"bytes": ref_bytes},
                    "citations": {"enabled": not is_docx}
                }
            })
        
        # Add comparison prompt
        content_blocks.append({
            "text": self._get_comparison_prompt(policy_name, ref_name, doc_type)
        })
        
        # Create fresh agent for this comparison (stateless)
        agent = self._create_agent()
        
        # Execute structured comparison
        result = await agent.structured_output_async(ComparisonResult, content_blocks)
        
        # Update result with document metadata
        result.document_name = ref_name
        result.document_type = doc_type
        result.document_path = ref_doc_path
        
        return result
    
    
    @staticmethod
    def _sanitize_document_name(name: str) -> str:
        """
        Sanitize document name for Bedrock compatibility.
        Only allows alphanumeric characters, whitespace, hyphens, parentheses, and square brackets.
        """
        import re
        
        # Replace disallowed characters with spaces
        sanitized = re.sub(r'[^a-zA-Z0-9\s\-\(\)\[\]]', ' ', name)
        
        # Replace multiple consecutive whitespace with single space
        sanitized = re.sub(r'\s+', ' ', sanitized)
        
        # Strip leading/trailing whitespace
        sanitized = sanitized.strip()
        
        # Limit length to be safe
        if len(sanitized) > 100:
            sanitized = sanitized[:100].strip()
        
        return sanitized
    
    def _get_comparison_prompt(self, policy_name: str, ref_name: str, doc_type: str) -> str:
        """Generate comparison prompt based on document type."""
        base_prompt = f"""Compare the policy document "{policy_name}" against the {doc_type} document "{ref_name}".

Analyze the policy for:
- Compliance gaps and legal requirements not met
- Missing provisions or unclear procedures  
- Areas where the policy could be improved
- Current best practices or trends (for news sources)

You must provide exactly 3 recommendations. Each recommendation should:
- Have a clear, actionable title
- Include detailed description of the issue and solution
- Specify priority level (HIGH for legal compliance, MEDIUM for process improvements, LOW for best practices)
- Provide specific implementation guidance
- Include exact citations from the reference document

Focus on practical improvements that address real policy gaps or compliance issues."""

        if doc_type == "legislation":
            return base_prompt + """

Pay special attention to:
- Legal obligations and statutory requirements
- Mandatory procedures and timelines
- Employee rights and protections
- Compliance requirements and penalties"""

        elif doc_type == "guidelines":
            return base_prompt + """

Pay special attention to:
- Best practice recommendations
- Industry standards and benchmarks
- Process improvements and clarity
- Implementation guidance and examples"""

        else:  # news
            return base_prompt + """

Pay special attention to:
- Current trends and emerging issues
- Recent developments and changes
- Common challenges and solutions
- Areas of public or regulatory focus"""
