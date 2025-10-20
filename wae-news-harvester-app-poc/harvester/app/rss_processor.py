
import asyncio
import feedparser
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
import json

from core.logging_config import get_logger
from core.models import HarvesterConfigTask, CrawlRSSTask, CrawlRequest, ProcessedRSSItem
from core.sqs_utils import AsyncBoto3SQS
from core.config import harvester_settings

logger = get_logger(__name__)

async def fetch_rss_tasks_from_dynamodb() -> List[Dict[str, Any]]:
    """
    Fetch all RSS crawl tasks from DynamoDB.

    Returns:
        List[Dict[str, Any]]: List of RSS crawl tasks as dictionaries
    """
    try:
        logger.info("RSS:fetch_rss_tasks_from_dynamodb: Fetching RSS tasks from DynamoDB")

        # Ensure table exists
        if not HarvesterConfigTask.exists():
            logger.warning("RSS:fetch_rss_tasks_from_dynamodb: DynamoDB table does not exist")
            return []

        # Use boto3 directly to avoid PynamoDB deserialization issues
        import boto3
        from boto3.dynamodb.conditions import Attr

        dynamodb = boto3.resource('dynamodb', region_name=harvester_settings.aws_region)
        table = dynamodb.Table(HarvesterConfigTask.Meta.table_name)

        # Scan for tasks with task_type = 'crawl_rss'
        response = table.scan(
            FilterExpression=Attr('task_type').eq('crawl_rss')
        )

        tasks = response.get('Items', [])

        # Get additional items if scan was paginated
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression=Attr('task_type').eq('crawl_rss'),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            tasks.extend(response.get('Items', []))

        logger.info(f"RSS:fetch_rss_tasks_from_dynamodb: Found {len(tasks)} RSS tasks")
        return tasks

    except Exception as e:
        logger.error(f"RSS:fetch_rss_tasks_from_dynamodb: Error fetching RSS tasks: {e}", exc_info=True)
        return []

async def parse_rss_feed(feed_url: str, max_items: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Parse an RSS feed and return its items.

    Args:
        feed_url: URL of the RSS feed
        max_items: Maximum number of items to return (None for all)

    Returns:
        List[Dict[str, Any]]: List of RSS feed items
    """
    try:
        logger.info(f"RSS:parse_rss_feed: Parsing RSS feed: {feed_url}")

        # Parse the feed
        feed = feedparser.parse(feed_url)

        if feed.bozo:
            logger.warning(f"RSS:parse_rss_feed: Feed parsing error: {feed.bozo_exception}")

        # Get the items
        items = feed.entries

        # Limit the number of items if specified
        if max_items is not None and max_items > 0:
            items = items[:max_items]

        logger.info(f"RSS:parse_rss_feed: Found {len(items)} items in feed")
        return items

    except Exception as e:
        logger.error(f"RSS:parse_rss_feed: Error parsing RSS feed {feed_url}: {e}", exc_info=True)
        return []

async def get_processed_urls(task_id: str) -> Set[str]:
    """
    Get a set of URLs that have already been processed for a specific RSS task.

    Args:
        task_id: The ID of the RSS task

    Returns:
        Set[str]: Set of processed URLs
    """
    try:
        # Check if the ProcessedRSSItem table exists
        if not ProcessedRSSItem.exists():
            logger.info("RSS:get_processed_urls: ProcessedRSSItem table does not exist, creating it")
            ProcessedRSSItem.create_table(wait=True)
            return set()

        # Query for processed URLs for this task
        processed_urls = set()
        for item in ProcessedRSSItem.query(task_id):
            processed_urls.add(item.url)

        logger.info(f"RSS:get_processed_urls: Found {len(processed_urls)} processed URLs for task {task_id}")
        return processed_urls

    except Exception as e:
        logger.error(f"RSS:get_processed_urls: Error getting processed URLs: {e}", exc_info=True)
        return set()

async def mark_url_as_processed(task_id: str, url: str) -> bool:
    """
    Mark a URL as processed for a specific RSS task.

    Args:
        task_id: The ID of the RSS task
        url: The URL that was processed

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create a new ProcessedRSSItem
        import time
        url_hash = hashlib.md5(url.encode()).hexdigest()

        processed_item = ProcessedRSSItem(
            task_id=task_id,
            url_hash=url_hash,
            url=url,
            processed_at=datetime.utcnow().isoformat()
        )

        # Save to DynamoDB
        processed_item.save()
        return True

    except Exception as e:
        logger.error(f"RSS:mark_url_as_processed: Error marking URL as processed: {e}", exc_info=True)
        return False

async def submit_rss_items_to_queue(
    sqs_helper: AsyncBoto3SQS,
    queue_url: str,
    task: Dict[str, Any],
    items: List[Dict[str, Any]]
) -> int:
    """
    Submit RSS feed items to the SQS queue for crawling.

    Args:
        sqs_helper: AsyncBoto3SQS helper
        queue_url: SQS queue URL
        task: The RSS task configuration
        items: List of RSS feed items

    Returns:
        int: Number of items successfully queued
    """
    try:
        logger.info(f"RSS:submit_rss_items_to_queue: Submitting {len(items)} items to queue")

        # Get task configuration from the dictionary
        config_data = task.get('config_data', {})
        if isinstance(config_data, str):
            try:
                config_data = json.loads(config_data)
            except json.JSONDecodeError:
                logger.error("RSS:submit_rss_items_to_queue: Failed to parse config_data JSON")
                config_data = {}

        # Get the link field name (default to 'link')
        link_field = config_data.get('item_link_field', 'link')

        # Get task ID
        task_id = task.get('task_id', '') or task.get('id', '')

        # Get already processed URLs if tracking is enabled
        processed_urls = set()
        if harvester_settings.rss_track_processed_urls:
            processed_urls = await get_processed_urls(task_id)
            logger.info(f"RSS:submit_rss_items_to_queue: Found {len(processed_urls)} already processed URLs for task {task_id}")

        # Track successfully queued items
        queued_count = 0

        for item in items:
            # Get the URL from the specified link field
            url = item.get(link_field)
            if not url:
                logger.warning(f"RSS:submit_rss_items_to_queue: Item missing URL in field '{link_field}'")
                continue

            # Skip already processed URLs if tracking is enabled
            if harvester_settings.rss_track_processed_urls and url in processed_urls:
                logger.debug(f"RSS:submit_rss_items_to_queue: Skipping already processed URL: {url}")
                continue

            # Create a unique ID for this item
            url_hash = hashlib.md5(url.encode()).hexdigest()[-8:]
            item_id = f"{task_id}-{url_hash}"

            # Create a crawl request
            crawl_request = CrawlRequest(
                type="crawl-single-url",
                url=url,
                id=item_id,
                tags=task.get('tags', []),
                save_pdf=config_data.get('save_pdf', True)
            )

            # Convert to JSON
            message_body = crawl_request.model_dump_json()

            # Send to SQS
            try:
                await sqs_helper.send_message(
                    queue_url=queue_url,
                    body=message_body,
                    message_attributes={
                        "MessageType": {
                            "DataType": "String",
                            "StringValue": "crawl-single-url"
                        },
                        "Source": {
                            "DataType": "String",
                            "StringValue": "rss-processor"
                        },
                        "TaskId": {
                            "DataType": "String",
                            "StringValue": task.get('task_id', '')
                        }
                    }
                )
                queued_count += 1
                logger.debug(f"RSS:submit_rss_items_to_queue: Queued URL: {url}")

                # Mark URL as processed if tracking is enabled
                if harvester_settings.rss_track_processed_urls:
                    await mark_url_as_processed(task_id, url)
            except Exception as e:
                logger.error(f"RSS:submit_rss_items_to_queue: Error queueing URL {url}: {e}")

        logger.info(f"RSS:submit_rss_items_to_queue: Successfully queued {queued_count} items")
        return queued_count

    except Exception as e:
        logger.error(f"RSS:submit_rss_items_to_queue: Error submitting items to queue: {e}", exc_info=True)
        return 0

async def process_rss_feeds(sqs_helper: AsyncBoto3SQS, queue_url: str) -> Dict[str, Any]:
    """
    Process all RSS feeds from the configuration table.

    Args:
        sqs_helper: AsyncBoto3SQS helper
        queue_url: SQS queue URL

    Returns:
        Dict[str, Any]: Processing results
    """
    try:
        logger.info("RSS:process_rss_feeds: Starting RSS feed processing")

        # Fetch RSS tasks
        tasks = await fetch_rss_tasks_from_dynamodb()

        if not tasks:
            logger.info("RSS:process_rss_feeds: No RSS tasks found")
            return {"status": "success", "message": "No RSS tasks found", "processed": 0}

        # Process each task
        total_processed = 0
        results = []

        for task in tasks:
            try:
                # Get task configuration from the dictionary
                config_data = task.get('config_data', {})
                if isinstance(config_data, str):
                    try:
                        config_data = json.loads(config_data)
                    except json.JSONDecodeError:
                        logger.error(f"RSS:process_rss_feeds: Failed to parse config_data JSON for task {task.get('task_id')}")
                        config_data = {}

                # Get feed URL and max items from config
                feed_url = config_data.get('feed_url')
                max_items = config_data.get('max_items')

                # Log the values for debugging
                logger.debug(f"RSS:process_rss_feeds: Task {task.get('task_id')} - feed_url: {feed_url}, max_items: {max_items} (type: {type(max_items).__name__})")

                # Ensure max_items is an integer if present
                if max_items is not None:
                    try:
                        max_items = int(max_items)
                    except (ValueError, TypeError):
                        logger.warning(f"RSS:process_rss_feeds: Invalid max_items value: {max_items}, using None")
                        max_items = None

                if not feed_url:
                    logger.error(f"RSS:process_rss_feeds: Missing feed_url for task {task.get('task_id')}")
                    results.append({
                        "task_id": task.get('task_id', 'unknown'),
                        "status": "error",
                        "message": "Missing feed_url in configuration",
                        "processed": 0
                    })
                    continue

                # Parse the feed
                items = await parse_rss_feed(
                    feed_url=feed_url,
                    max_items=max_items
                )

                if not items:
                    logger.warning(f"RSS:process_rss_feeds: No items found in feed for task {task.get('task_id')}")
                    results.append({
                        "task_id": task.get('task_id', 'unknown'),
                        "status": "warning",
                        "message": "No items found in feed",
                        "processed": 0
                    })
                    continue

                # Submit items to queue
                processed = await submit_rss_items_to_queue(
                    sqs_helper=sqs_helper,
                    queue_url=queue_url,
                    task=task,
                    items=items
                )

                # Add result
                results.append({
                    "task_id": task.get('task_id', 'unknown'),
                    "status": "success",
                    "message": f"Processed {processed} items",
                    "processed": processed
                })

                total_processed += processed

            except Exception as e:
                logger.error(f"RSS:process_rss_feeds: Error processing task {task.get('task_id', 'unknown')}: {e}", exc_info=True)
                results.append({
                    "task_id": task.get('task_id', 'unknown'),
                    "status": "error",
                    "message": f"Error: {str(e)}",
                    "processed": 0
                })

        logger.info(f"RSS:process_rss_feeds: Completed processing {len(tasks)} tasks, {total_processed} items queued")
        return {
            "status": "success",
            "message": f"Processed {len(tasks)} RSS feeds",
            "processed": total_processed,
            "results": results
        }

    except Exception as e:
        logger.error(f"RSS:process_rss_feeds: Error processing RSS feeds: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Error processing RSS feeds: {str(e)}",
            "processed": 0
        }

# Schedule periodic RSS feed processing
async def schedule_rss_feed_processing(
    sqs_helper: AsyncBoto3SQS,
    queue_url: str,
    interval_seconds: int = None  # Will use the configured value or default
):
    # Use the configured interval or default to 600 seconds (10 minutes)
    if interval_seconds is None:
        interval_seconds = harvester_settings.rss_processing_interval_seconds or 600
    """
    Schedule periodic RSS feed processing.

    Args:
        sqs_helper: AsyncBoto3SQS helper
        queue_url: SQS queue URL
        interval_seconds: Interval between processing runs in seconds
    """
    logger.info(f"RSS:schedule_rss_feed_processing: Starting RSS feed scheduler with interval {interval_seconds}s")

    while True:
        try:
            # Process RSS feeds
            result = await process_rss_feeds(sqs_helper, queue_url)
            logger.info(f"RSS:schedule_rss_feed_processing: Completed processing cycle: {result['message']}")

            # Wait for the next interval
            await asyncio.sleep(interval_seconds)

        except Exception as e:
            logger.error(f"RSS:schedule_rss_feed_processing: Error in processing cycle: {e}", exc_info=True)
            # Wait a bit before retrying after an error
            await asyncio.sleep(60)
