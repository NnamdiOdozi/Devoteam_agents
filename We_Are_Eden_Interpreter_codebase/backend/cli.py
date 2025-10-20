#!/usr/bin/env python3

import asyncio
import json
import sys
from pathlib import Path
import click

from backend.assessor import PolicyAssessor
from backend.models import PolicyAssessmentResult


@click.command()
@click.option(
    '--policy', 
    default='data/Customer/NHS (Monitor, Independent regulator of NHS foundation trusts) - Maternity, Paternity and Adoption Policy.pdf',
    help='Path to the policy document to assess'
)
@click.option(
    '--category', 
    default='maternity',
    type=click.Choice(['maternity', 'fertility', 'menopause', 'breastfeeding']),
    help='Category of the policy document'
)
@click.option(
    '--output',
    help='Output file path for the assessment results (JSON format). If not specified, prints to stdout.'
)
def assess_policy(policy: str, category: str, output: str):
    """
    Assess a company policy document against legislation, guidelines, and news for the specified category.
    
    This tool compares your policy document against relevant reference documents and provides
    actionable recommendations to improve compliance and best practices.
    
    Examples:
    
    \b
    # Use defaults (NHS maternity policy)
    python main.py
    
    \b
    # Assess a fertility policy
    python main.py --policy "data/Customer/Manchester Univ - Time off for Fertility Treatment Policy.pdf" --category fertility
    
    \b
    # Save results to file
    python main.py --output assessment_results.json
    """
    # Validate policy file exists
    if not Path(policy).exists():
        click.echo(f"Error: Policy file not found: {policy}", err=True)
        sys.exit(1)
    
    click.echo("Starting policy assessment...")
    click.echo(f"Policy: {Path(policy).name}")
    click.echo(f"Category: {category}\n")
    
    try:
        # Run the assessment
        result = asyncio.run(_run_assessment(policy, category))
        
        # Output results
        if output:
            _save_results(result, output)
            click.echo(f"\nAssessment results saved to: {output}")
        else:
            _print_results(result)
            
    except Exception as e:
        click.echo(f"Error during assessment: {e}", err=True)
        raise


async def _run_assessment(policy_path: str, category: str) -> PolicyAssessmentResult:
    """Run the policy assessment asynchronously."""
    assessor = PolicyAssessor()
    return await assessor.assess_policy(policy_path, category)


def _save_results(result: PolicyAssessmentResult, output_path: str):
    """Save assessment results to JSON file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)


def _print_results(result: PolicyAssessmentResult):
    """Print formatted assessment results to stdout."""
    click.echo("="*80)
    click.echo(f"POLICY ASSESSMENT REPORT")
    click.echo("="*80)
    click.echo(f"Policy: {result.policy_name}")
    click.echo(f"Category: {result.category.upper()}")
    click.echo(f"Assessment Date: {result.assessment_date}")
    click.echo(f"Documents Compared: {result.total_documents_compared}")
    click.echo(f"Total Recommendations: {result.total_recommendations}")
    click.echo("="*80)
    
    # Group by document type and print directly
    legislation_docs = [r for r in result.results if r.document_type == "legislation"]
    guidelines_docs = [r for r in result.results if r.document_type == "guidelines"]
    news_docs = [r for r in result.results if r.document_type == "news"]
    
    if legislation_docs:
        _print_document_section("📋 LEGISLATION COMPLIANCE", legislation_docs)
    if guidelines_docs:
        _print_document_section("📘 BEST PRACTICE GUIDELINES", guidelines_docs)
    if news_docs:
        _print_document_section("📰 CURRENT TRENDS & NEWS", news_docs)


def _print_priority_section(title: str, recommendations: list):
    """Print a section of recommendations grouped by priority."""
    if not recommendations:
        return
        
    click.echo(f"\n{title}")
    click.echo("-" * len(title))
    
    for i, (comparison, rec) in enumerate(recommendations, 1):
        click.echo(f"\n{i}. {rec.title}")
        click.echo(f"   Source: {comparison.document_name} ({comparison.document_type})")
        click.echo(f"   Description: {rec.description}")
        click.echo(f"   Implementation: {rec.implementation_guidance}")
        click.echo(f"   Citation: {rec.source_citation}")


def _print_document_section(title: str, documents: list):
    """Print a section of documents with their recommendations."""
    click.echo(f"\n{title}")
    click.echo("-" * len(title))
    
    for doc in documents:
        click.echo(f"\n📄 {doc.document_name}")
        for i, rec in enumerate(doc.recommendations, 1):
            click.echo(f"   {i}. [{rec.priority}] {rec.title}")
            click.echo(f"      {rec.description}")


if __name__ == '__main__':
    assess_policy()
