# helpers_sqs_boto3.py
from typing import Any, Dict, List, Optional
import asyncio
import boto3

class AsyncBoto3SQS:
    def __init__(self, sqs_client):
        self.sqs = sqs_client  # share one client created at startup

    async def send_message(
        self,
        queue_url: str,
        body: str,
        *,
        message_attributes: Optional[Dict[str, Any]] = None,
        delay_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"QueueUrl": queue_url, "MessageBody": body}
        if message_attributes:
            params["MessageAttributes"] = message_attributes
        if delay_seconds is not None:
            params["DelaySeconds"] = delay_seconds
        return await asyncio.to_thread(self.sqs.send_message, **params)

    async def send_messages_batch(
        self,
        queue_url: str,
        entries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for i in range(0, len(entries), 10):
            chunk = entries[i : i + 10]
            resp = await asyncio.to_thread(self.sqs.send_message_batch, QueueUrl=queue_url, Entries=chunk)
            results.append(resp)
        return results

    async def receive_messages(
        self,
        queue_url: str,
        *,
        max_number: int = 10,
        wait_time: int = 20,
        visibility_timeout: Optional[int] = None,
        attribute_names: Optional[List[str]] = None,
        message_attribute_names: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "QueueUrl": queue_url,
            "MaxNumberOfMessages": max(1, min(max_number, 10)),
            "WaitTimeSeconds": max(0, min(wait_time, 20)),
            "MessageAttributeNames": message_attribute_names or ["All"],
        }
        if visibility_timeout is not None:
            params["VisibilityTimeout"] = visibility_timeout
        if attribute_names:
            params["AttributeNames"] = attribute_names
        resp = await asyncio.to_thread(self.sqs.receive_message, **params)
        return resp.get("Messages", [])

    async def delete_message(self, queue_url: str, receipt_handle: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self.sqs.delete_message, QueueUrl=queue_url, ReceiptHandle=receipt_handle)

    async def delete_messages_batch(self, queue_url: str, receipt_handles: List[str]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for i in range(0, len(receipt_handles), 10):
            entries = [{"Id": str(j), "ReceiptHandle": rh} for j, rh in enumerate(receipt_handles[i : i + 10])]
            resp = await asyncio.to_thread(self.sqs.delete_message_batch, QueueUrl=queue_url, Entries=entries)
            results.append(resp)
        return results

    async def change_message_visibility(
        self, queue_url: str, receipt_handle: str, visibility_timeout: int
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.sqs.change_message_visibility,
            QueueUrl=queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=visibility_timeout,
        )

    async def get_queue_attributes(
        self, queue_url: str, attribute_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Get queue attributes including message counts and queue configuration."""
        if attribute_names is None:
            # Get all available attributes
            attribute_names = [
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
                "ApproximateNumberOfMessagesDelayed",
                "QueueArn",
                "CreatedTimestamp",
                "LastModifiedTimestamp",
                "VisibilityTimeout",
                "MessageRetentionPeriod",
                "DelaySeconds",
                "ReceiveMessageWaitTimeSeconds",
                "RedrivePolicy"
            ]

        params = {
            "QueueUrl": queue_url,
            "AttributeNames": attribute_names
        }

        return await asyncio.to_thread(self.sqs.get_queue_attributes, **params)
