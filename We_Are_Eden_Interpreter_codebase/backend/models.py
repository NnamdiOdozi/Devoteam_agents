#!/usr/bin/env python3

from pydantic import BaseModel, Field
from typing import List, Literal
from datetime import datetime


class Recommendation(BaseModel):
    """A single policy recommendation extracted from document comparison."""
    
    title: str = Field(description="Clear, actionable title for the recommendation")
    description: str = Field(description="Detailed description of the issue and recommended action")
    priority: Literal["HIGH", "MEDIUM", "LOW"] = Field(description="Priority level based on legal/compliance risk")
    implementation_guidance: str = Field(description="Specific guidance on how to implement this recommendation")
    source_citation: str = Field(description="Exact citation or reference from the source document")


class ComparisonResult(BaseModel):
    """Result of comparing a policy against a single reference document."""
    
    document_name: str = Field(description="Name of the reference document")
    document_type: Literal["legislation", "guidelines", "news"] = Field(description="Type of reference document")
    document_path: str = Field(description="File path of the reference document")
    recommendations: List[Recommendation] = Field(
        description="Exactly 3 recommendations extracted from this comparison",
        min_length=3,
        max_length=3
    )


class PolicyAssessmentResult(BaseModel):
    """Complete assessment result for a policy document."""
    
    policy_name: str = Field(description="Name of the policy being assessed")
    policy_path: str = Field(description="File path of the policy document")
    category: Literal["maternity", "fertility", "menopause", "breastfeeding"] = Field(description="Policy category")
    assessment_date: str = Field(description="Date when assessment was performed")
    total_documents_compared: int = Field(description="Total number of reference documents compared")
    total_recommendations: int = Field(description="Total number of recommendations generated")
    results: List[ComparisonResult] = Field(description="Individual comparison results")
    
    @classmethod
    def create(cls, policy_name: str, policy_path: str, category: str, results: List[ComparisonResult]) -> "PolicyAssessmentResult":
        """Create a PolicyAssessmentResult with calculated totals."""
        return cls(
            policy_name=policy_name,
            policy_path=policy_path,
            category=category,
            assessment_date=datetime.now().strftime("%Y-%m-%d"),
            total_documents_compared=len(results),
            total_recommendations=len(results) * 3,  # Always 3 per document
            results=results
        )
