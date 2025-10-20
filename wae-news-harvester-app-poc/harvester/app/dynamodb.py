from typing import List, Optional, Dict, Any
from core.config import harvester_settings
from core.logging_config import get_logger
from core.models import HarvesterConfig, HarvesterConfigTask, HarvesterTask, CrawledWebsite
import json
import time
from pathlib import Path

logger = get_logger(__name__)

# Crawled Website Storage Functions

async def store_crawled_website_in_dynamodb(
    url: str,
    url_hash: str,
    article: Dict[str, Any],
    save_paths: Dict[str, str],
    success: bool = True,
    error: str = None
) -> bool:
    """
    Store crawled website information in DynamoDB.

    Args:
        url: The URL that was crawled
        url_hash: Hash of the URL (used as primary key)
        article: Extracted article data (title, body, etc.)
        save_paths: Dictionary of paths where files were saved (json, text, pdf)
        success: Whether the crawl was successful
        error: Error message if the crawl failed

    Returns:
        bool: True if stored successfully, False otherwise
    """
    try:
        # Ensure table exists
        if not CrawledWebsite.exists():
            logger.info("CRAWL:store_crawled_website_in_dynamodb: Creating DynamoDB table...")
            CrawledWebsite.create_table(wait=True)
            logger.info("CRAWL:store_crawled_website_in_dynamodb: DynamoDB table created successfully")

        # Create and save the crawled website record
        ttl_seconds = harvester_settings.dynamodb_task_ttl_secs
        crawled_site = CrawledWebsite.from_crawl_result(
            url=url,
            url_hash=url_hash,
            article=article,
            save_paths=save_paths,
            success=success,
            error=error,
            ttl_seconds=ttl_seconds
        )

        crawled_site.save()
        logger.info(f"CRAWL:store_crawled_website_in_dynamodb: Stored crawled website in DynamoDB: {url}")
        return True

    except Exception as e:
        logger.error(f"CRAWL:store_crawled_website_in_dynamodb: Error storing crawled website in DynamoDB: {e}", exc_info=True)
        return False
