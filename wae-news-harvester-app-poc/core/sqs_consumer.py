from typing import Callable, Awaitable, Dict, Any, Optional, List
import asyncio
import json
from .sqs_utils import AsyncBoto3SQS
from .logging_config import get_logger

# Get logger with centralized configuration
logger = get_logger(__name__)


class SQSConsumer:
    def __init__(
        self,
        helper: AsyncBoto3SQS,
        queue_url: str,
        *,
        concurrency: int = 5,
        wait_time: int = 20,
        max_number: int = 10,
        visibility_timeout: Optional[int] = None,
        heartbeat_every: Optional[int] = None,  # seconds; extend visibility if set
        process_func: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ):
        self.helper = helper
        self.queue_url = queue_url
        self.wait_time = wait_time
        self.max_number = max_number
        self.visibility_timeout = visibility_timeout
        self.heartbeat_every = heartbeat_every
        self.process_func = process_func or self.default_process
        self._sem = asyncio.Semaphore(concurrency)
        self._running = asyncio.Event()
        self._not_paused = asyncio.Event()
        self._not_paused.set()
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        logger.debug("SQS:SQSConsumer:start: Starting SQS Consumer task.")
        self._running.set()
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        logger.debug("SQS:SQSConsumer:stop: Stopping SQS Consumer task.")
        self._running.clear()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def is_running(self) -> bool:
        return self._running.is_set()

    async def pause(self):
        self._not_paused.clear()

    async def resume(self):
        self._not_paused.set()

    async def _run(self):
        try:
            while self._running.is_set():
                await self._not_paused.wait()
                messages = await self.helper.receive_messages(
                    self.queue_url,
                    max_number=self.max_number,
                    wait_time=self.wait_time,
                    visibility_timeout=self.visibility_timeout,
                )
                if not messages:
                    continue
                for msg in messages:
                    await self._sem.acquire()
                    asyncio.create_task(self._handle_message(msg))
        except asyncio.CancelledError:
            # graceful exit
            raise

    async def _handle_message(self, msg: Dict[str, Any]):
        try:
            # Optionally run a heartbeat task to extend visibility
            hb_task: Optional[asyncio.Task] = None
            if self.heartbeat_every and self.visibility_timeout:
                hb_task = asyncio.create_task(self._heartbeat(msg["ReceiptHandle"]))
            try:
                await self.process_func(msg)
            finally:
                if hb_task:
                    hb_task.cancel()
                    try:
                        await hb_task
                    except asyncio.CancelledError:
                        pass
        except Exception as e:
            logger.exception(f"Error processing message: {msg.get('MessageId', 'unknown')}: {e}")
            pass
        finally:
            self._sem.release()

    async def _heartbeat(self, receipt_handle: str):
        # periodically extend visibility while processing
        try:
            while True:
                await asyncio.sleep(self.heartbeat_every)
                await self.helper.change_message_visibility(
                    self.queue_url, receipt_handle, self.visibility_timeout
                )
        except asyncio.CancelledError:
            raise

    async def default_process(self, msg: Dict[str, Any]):
        # placeholder processing; replace with real logic
        await asyncio.sleep(0.1)

    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive SQS consumer and queue status information."""
        try:
            # Get consumer status
            running = self.is_running()
            paused = not self._not_paused.is_set()

            # Get queue attributes
            queue_attributes = await self.helper.get_queue_attributes(self.queue_url)

            # Extract queue name from URL
            queue_name = self.queue_url.split('/')[-1]

            # Parse attributes for easier consumption
            attributes = queue_attributes.get("Attributes", {})

            # Safely parse redrive policy JSON
            redrive_policy = attributes.get("RedrivePolicy")
            if redrive_policy:
                try:
                    redrive_policy = json.loads(redrive_policy)
                except (json.JSONDecodeError, TypeError):
                    redrive_policy = None

            return {
                "task_running": running,
                "task_paused": paused,
                "queue_info": {
                    "queue_name": queue_name,
                    "queue_url": self.queue_url,
                    "queue_arn": attributes.get("QueueArn"),
                    "messages_available": int(attributes.get("ApproximateNumberOfMessages", 0)),
                    "messages_in_flight": int(attributes.get("ApproximateNumberOfMessagesNotVisible", 0)),
                    "messages_delayed": int(attributes.get("ApproximateNumberOfMessagesDelayed", 0)),
                    "visibility_timeout": int(attributes.get("VisibilityTimeout", 0)),
                    "message_retention_period": int(attributes.get("MessageRetentionPeriod", 0)),
                    "delay_seconds": int(attributes.get("DelaySeconds", 0)),
                    "receive_message_wait_time": int(attributes.get("ReceiveMessageWaitTimeSeconds", 0)),
                    "created_timestamp": attributes.get("CreatedTimestamp"),
                    "last_modified_timestamp": attributes.get("LastModifiedTimestamp"),
                    "redrive_policy": redrive_policy
                }
            }
        except Exception as e:
            logger.error(f"Error getting SQS status: {e}")
            raise
