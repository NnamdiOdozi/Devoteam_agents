from fastapi import APIRouter, HTTPException, Request, Body, Depends
from fastapi.responses import JSONResponse
from typing import List, Dict, Any
import uuid
import json
from datetime import datetime
from core.sqs_consumer import SQSConsumer
from ..bedrock_token import BedrockToken, get_app
from ..crawler import crawl_urls, crawl_url_for_response

from core.models import (
    ErrorResponse,
    SQSMessageRequest,
    CrawlRSSTask,
    HarvesterConfigTask,
    CrawlRequest
)

from core.logging_config import get_logger, get_logger_with_session

# Get logger with centralized configuration
logger = get_logger(__name__)

router = APIRouter()

def get_consumer(request: Request) -> SQSConsumer:
    return request.app.state.sqs_consumer

@router.get("/sqs/status", tags=["SQS"])
async def consumer_status(consumer = Depends(get_consumer)):
    try:
        return await consumer.get_status()
    except Exception as e:
        logger.error(f"Error getting SQS status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get SQS status: {str(e)}")

@router.get("/sqs/pause", tags=["SQS"])
async def consumer_pause(consumer = Depends(get_consumer)):
    try:
        logger.info("SQS:api:endpoints:consumer_pause: Pausing SQS Queue Ingest")
        await consumer.pause()
        return await consumer.get_status()
    except Exception as e:
        logger.error(f"Error pausing SQS consumer: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to pause SQS consumer: {str(e)}")

@router.get("/sqs/resume", tags=["SQS"])
async def consumer_resume(consumer = Depends(get_consumer)):
    try:
        logger.info("SQS:api:endpoints:consumer_resume: Resuming SQS Queue Ingest")
        await consumer.resume()
        return await consumer.get_status()
    except Exception as e:
        logger.error(f"Error resuming SQS consumer: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resume SQS consumer: {str(e)}")

@router.post("/sqs/send_message", tags=["SQS"])
async def send_message(request: Request, req: SQSMessageRequest = Body(...)):
    try:
        resp = await request.app.state.sqs_helper.send_message(
            queue_url=request.app.state.queue_url,
            body=req.body,
            message_attributes=req.message_attributes,
            delay_seconds=req.delay_seconds,
        )
        return {"message_id": resp.get("MessageId")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    payload = {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
    return JSONResponse(content=payload)


@router.get("/bedrock/token", tags=["Bedrock"])
async def get_token(request: Request):
    app = get_app()
    token = app.state.bedrock_api_token
    return {"token": token }

@router.post("/crawl/rss", tags=["Configuration"])
async def add_rss_crawl_task(request: Request, rss_task: CrawlRSSTask = Body(...)):
    """
    Add a new RSS crawl task to the DynamoDB configuration table.

    Args:
        rss_task: CrawlRSSTask containing RSS feed configuration

    Returns:
        Dict with task details and creation status
    """
    try:
        logger.info(f"API:add_rss_crawl_task: Adding RSS crawl task: {rss_task.id}")

        # Validate the task (Pydantic will handle this automatically)
        # Additional validation: ensure task ID is unique
        try:
            existing_task = HarvesterConfigTask.get(rss_task.id)
            logger.warning(f"API:add_rss_crawl_task: Task ID '{rss_task.id}' already exists")
            raise HTTPException(
                status_code=409,
                detail=f"Task with ID '{rss_task.id}' already exists. Use a unique task ID."
            )
        except HarvesterConfigTask.DoesNotExist:
            # This is expected - task doesn't exist, so we can create it
            pass

        # Get configuration version from app state (fallback to "1" if not available)
        config_version = "1"
        if hasattr(request.app.state, 'harvester_config'):
            config_version = request.app.state.harvester_config.version

        # Create DynamoDB entry
        db_task = HarvesterConfigTask.from_pydantic_task(rss_task, config_version)

        # Ensure table exists
        if not HarvesterConfigTask.exists():
            logger.info("API:add_rss_crawl_task: Creating DynamoDB table...")
            HarvesterConfigTask.create_table(wait=True)
            logger.info("API:add_rss_crawl_task: DynamoDB table created successfully")

        # Save to DynamoDB
        db_task.save()

        logger.info(f"API:add_rss_crawl_task: Successfully added RSS task '{rss_task.id}' to DynamoDB")

        return {
            "status": "success",
            "message": f"RSS crawl task '{rss_task.id}' added successfully",
            "task": {
                "id": rss_task.id,
                "type": rss_task.type,
                "feed_url": str(rss_task.feed_url),
                "tags": rss_task.tags,
                "max_items": rss_task.max_items,
                "only_new": rss_task.only_new,
                "save_pdf": rss_task.save_pdf,
                "created_at": db_task.created_at,
                "version": config_version
            }
        }

    except HTTPException:
        # Re-raise HTTP exceptions (like 409 for duplicate ID)
        raise
    except Exception as e:
        logger.error(f"API:add_rss_crawl_task: Error adding RSS task: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add RSS crawl task: {str(e)}"
        )

@router.post("/crawl/url", tags=["Crawler"])
async def crawl_single_url(request: Request, crawl_task: CrawlRequest = Body(...)):
    """
    Queue a URL for crawling by sending a message to the SQS queue.

    Args:
        crawl_task: CrawlRequest containing the URL to crawl

    Returns:
        Dict with queuing status
    """
    try:
        logger.info(f"API:crawl_single_url: Queueing URL for crawling: {crawl_task.url}")

        # Prepare the message to send to SQS
        # Use model_dump_json() to properly handle HttpUrl serialization
        message_body = crawl_task.model_dump_json()

        # Send the message to the SQS queue
        resp = await request.app.state.sqs_helper.send_message(
            queue_url=request.app.state.queue_url,
            body=message_body,
            message_attributes={
                "MessageType": {
                    "DataType": "String",
                    "StringValue": "crawl-single-url"
                }
            }
        )

        logger.info(f"API:crawl_single_url: Successfully queued URL: {crawl_task.url}, Message ID: {resp.get('MessageId')}")

        return {
            "status": "queued",
            "message": f"URL '{crawl_task.url}' queued for crawling",
            "message_id": resp.get("MessageId"),
            "task": {
                "id": crawl_task.id,
                "type": crawl_task.type,
                "url": str(crawl_task.url),
                "tags": crawl_task.tags,
                "save_pdf": crawl_task.save_pdf
            }
        }

    except Exception as e:
        logger.error(f"API:crawl_single_url: Error queueing URL: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue URL for crawling: {str(e)}"
        )

@router.post("/crawl/url_response", tags=["Crawler"])
async def crawl_single_url_response(request: Request, crawl_task: CrawlRequest = Body(...)):
    """
    Crawl a single URL and return the article content as JSON response.
    Uses the same underlying crawler code as /crawl/url but returns the JSON directly
    instead of queuing the task and saving to files.

    Args:
        crawl_task: CrawlRequest containing the URL to crawl

    Returns:
        Dict with the article content (same format as article.json)
    """
    try:
        logger.info(f"API:crawl_single_url_response: Crawling URL for response: {crawl_task.url}")

        # Crawl the URL and get the article data directly
        # Note: S3 helper not needed for response-only mode
        article_data = await crawl_url_for_response(
            url=str(crawl_task.url),
            s3_helper=None,
            request=request
        )

        logger.info(f"API:crawl_single_url_response: Successfully crawled URL: {crawl_task.url}")

        return {
            "status": "success",
            "message": f"Successfully crawled URL: {crawl_task.url}",
            "article": article_data
        }

    except Exception as e:
        logger.error(f"API:crawl_single_url_response: Error crawling URL: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to crawl URL: {str(e)}"
        )
