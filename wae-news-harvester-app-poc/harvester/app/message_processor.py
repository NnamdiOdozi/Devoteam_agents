import json
import asyncio
from typing import Dict, Any
from core.sqs_consumer import SQSConsumer
from core.logging_config import get_logger
from core.models import CrawlRequest
from .crawler import crawl_urls
from .bedrock_token import get_app
from core.config import harvester_settings

# Semaphore to ensure only one crawl_urls operation runs at a time
crawl_semaphore = asyncio.Semaphore(1)
logger = get_logger(__name__)

class RetryableError(Exception):
    pass

class NonRetryableError(Exception):
    pass

class IdempotencyStore:
    def __init__(self):
        self._seen = set()

    async def claim(self, event_id: str) -> bool:
        if event_id in self._seen:
            return False
        self._seen.add(event_id)
        return True

class HarvesterSQSConsumer(SQSConsumer):
    """Custom SQS Consumer with built-in message processing logic"""

    def __init__(self, *args, **kwargs):
        # Remove process_func from kwargs since we'll override it
        kwargs.pop('process_func', None)
        super().__init__(*args, **kwargs)

        # Initialize our processing components
        self.idem = IdempotencyStore()
        self.handlers = {
            "crawl-single-url": self.handle_crawl_single_url,
        }
        # Override the process_func to use our method
        self.process_func = self.process_message

    def parse_message(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        """Parse JSON message body"""
        try:
            return json.loads(msg["Body"])
        except json.JSONDecodeError:
            logger.error(f"SQS:parse_message: Invalid JSON in message {msg['MessageId']}")
            logger.debug(f"SQS:parse_message: Marking SQS message {msg['MessageId']} as non-retryable.")
            raise NonRetryableError("Invalid JSON format")

    async def process_message(self, msg: Dict[str, Any]) -> None:
        """Main message processing logic with access to self.helper and self.queue_url"""
        try:
            body = self.parse_message(msg)
        except NonRetryableError:
            return  # Let AWS route to DLQ after 1 attempt

        # Validate required fields
        try:
            message_valid = CrawlRequest.model_validate(body)
        except NonRetryableError:
            return  # Let AWS route to DLQ after 1 attempt

        event_id = body.get("id") or body.get("event_id") or msg["MessageId"]

        if not await self.idem.claim(event_id):
            # Already processed - delete to prevent re-processing
            await self.helper.delete_message(self.queue_url, msg["ReceiptHandle"])
            return

        event_type = body.get("type")
        handler = self.handlers.get(event_type)
        if handler is None:
            logger.error(f"SQS:process_message: No handler for message type: '{event_type}' in message {msg['MessageId']}")
            logger.debug(f"SQS:process_message: Available handlers: {list(self.handlers.keys())}")
            raise NonRetryableError(f"Unknown message type: {event_type}")

        try:
            await handler(body)
            logger.debug(f"SQS:process_message: Deleting SQS as processed succesfully: {msg['ReceiptHandle']}")
            await self.helper.delete_message(self.queue_url, msg["ReceiptHandle"])
        except RetryableError:
            # For retryable errors, we need to update the message body with the retry count
            # and then change the visibility timeout to allow for retry
            try:
                # Get the updated body with retry information
                updated_body = json.dumps(body)

                # Change message visibility for retry
                rc = self.get_receive_count(msg)
                delay = self.compute_backoff_seconds(rc)

                # First delete the original message
                await self.helper.delete_message(self.queue_url, msg["ReceiptHandle"])

                # Then send a new message with the updated body
                await self.helper.send_message(
                    queue_url=self.queue_url,
                    body=updated_body,
                    message_attributes=msg.get("MessageAttributes", {}),
                    delay_seconds=delay
                )

                logger.info(f"SQS:process_message: Message requeued for retry with updated retry count")
            except Exception as e:
                logger.error(f"SQS:process_message: Error updating message for retry: {e}", exc_info=True)
                # Fall back to just changing visibility if we can't update the message
                await self.helper.change_message_visibility(self.queue_url, msg["ReceiptHandle"], delay)
        except NonRetryableError:
            pass  # Let DLQ handle it

    def get_receive_count(self, msg: Dict[str, Any]) -> int:
        """Get message receive count for backoff calculation"""
        try:
            return int(msg.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
        except Exception:
            return 1

    def compute_backoff_seconds(self, receive_count: int) -> int:
        """Calculate exponential backoff delay"""
        return min(900, 2 ** min(receive_count, 8))

    # Message handlers
    async def handle_crawl_single_url(self, payload: Dict[str, Any]) -> None:
        """
        Process a single URL crawl request from SQS.

        Args:
            payload: The message payload containing the crawl request
        """
        try:
            logger.info(f"SQS:handle_single_url: Processing single URL: {payload}")

            # Convert payload to CrawlRequest
            crawl_task = CrawlRequest.model_validate(payload)

            # Get the app to access state
            app = get_app()

            # Define save location
            save_location = f"{harvester_settings.crawl_save_location}/{crawl_task.id}"

            # Acquire semaphore to ensure only one crawl_urls operation runs at a time
            logger.info(f"SQS:handle_single_url: Waiting for semaphore to crawl URL: {crawl_task.url}")
            async with crawl_semaphore:
                logger.info(f"SQS:handle_single_url: Starting crawl for URL: {crawl_task.url}")
                results = await crawl_urls(
                    urls=str(crawl_task.url),
                    save_location=save_location,
                    s3_helper=app.state.s3_helper if hasattr(app.state, "s3_helper") else None
                )

                # Check if crawling was successful
                if not results or len(results) == 0:
                    raise Exception(f"No results returned for URL: {crawl_task.url}")

                # Log success only if we got here without exceptions
                logger.info(f"SQS:handle_single_url: Successfully crawled URL: {crawl_task.url}")
                logger.debug(f"SQS:handle_single_url: Crawl results: {results}")

        except Exception as e:
            logger.error(f"SQS:handle_single_url: Error processing URL {payload.get('url', 'unknown')}: {e}", exc_info=True)

            # Check if this is already a retry attempt
            retry_count = payload.get("retry_count", 0)

            if retry_count < 1:  # Allow one retry
                # Increment retry count and mark for retry
                logger.info(f"SQS:handle_single_url: Marking for retry (attempt {retry_count + 1}): {payload.get('url')}")
                payload["retry_count"] = retry_count + 1
                payload["retry"] = True
                raise RetryableError(f"Transient processing error: {str(e)}")
            else:
                # Already retried once, mark as non-retryable
                logger.warning(f"SQS:handle_single_url: Max retries reached for URL: {payload.get('url')}")
                raise NonRetryableError(f"Failed to process URL after retry: {str(e)}")