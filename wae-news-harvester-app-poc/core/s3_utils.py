
from typing import Any, Dict, List, Optional, AsyncIterator
import asyncio
import io
from botocore.config import Config
import boto3

class AsyncBoto3S3:
    def __init__(self, s3_client):
        self.s3 = s3_client  # share one client created at startup

    # Upload a local file using managed transfer (multipart as needed)
    async def upload_file(
        self,
        bucket: str,
        key: str,
        filename: str,
        *,
        extra_args: Optional[Dict[str, Any]] = None,
        config: Optional[Any] = None,  # boto3.s3.transfer.TransferConfig
    ) -> None:
        await asyncio.to_thread(
            self.s3.upload_file,
            filename, bucket, key,
            ExtraArgs=extra_args,
            Config=config,
        )

    # Upload bytes via file-like object
    async def upload_bytes(
        self,
        bucket: str,
        key: str,
         bytes,
        *,
        extra_args: Optional[Dict[str, Any]] = None,
        config: Optional[Any] = None,
    ) -> None:
        bio = io.BytesIO(data)
        await asyncio.to_thread(
            self.s3.upload_fileobj,
            bio, bucket, key,
            ExtraArgs=extra_args,
            Config=config,
        )

    # Download to local file using managed transfer
    async def download_file(
        self,
        bucket: str,
        key: str,
        filename: str,
        *,
        extra_args: Optional[Dict[str, Any]] = None,
        config: Optional[Any] = None,
    ) -> None:
        await asyncio.to_thread(
            self.s3.download_file,
            bucket, key, filename,
            ExtraArgs=extra_args,
            Config=config,
        )

    # Read small/medium objects fully into memory
    async def get_object_bytes(
        self,
        bucket: str,
        key: str,
        *,
        byte_range: Optional[str] = None,  # e.g. "bytes=0-1048575"
    ) -> bytes:
        params = {"Bucket": bucket, "Key": key}
        if byte_range:
            params["Range"] = byte_range
        resp = await asyncio.to_thread(self.s3.get_object, **params)
        body = resp["Body"]
        return await asyncio.to_thread(body.read)

    # Async iterator over objects (list_objects_v2 pagination)
    async def iter_objects(
        self,
        bucket: str,
        *,
        prefix: Optional[str] = None,
        max_keys: int = 1000,
    ) -> AsyncIterator[Dict[str, Any]]:
        token: Optional[str] = None
        while True:
            kwargs: Dict[str, Any] = {"Bucket": bucket, "MaxKeys": max_keys}
            if prefix:
                kwargs["Prefix"] = prefix
            if token:
                kwargs["ContinuationToken"] = token
            resp = await asyncio.to_thread(self.s3.list_objects_v2, **kwargs)
            for obj in resp.get("Contents", []):
                yield obj
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")

    # Single delete
    async def delete_object(self, bucket: str, key: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self.s3.delete_object, Bucket=bucket, Key=key)

    # Batch delete (chunks of 1000)
    async def delete_objects_batch(self, bucket: str, keys: List[str]) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for i in range(0, len(keys), 1000):
            chunk = keys[i : i + 1000]
            resp = await asyncio.to_thread(
                self.s3.delete_objects,
                Bucket=bucket,
                Delete={"Objects": [{"Key": k} for k in chunk]},
            )
            results.append(resp)
        return results

    # Metadata only (exists/size/etag/headers)
    async def head_object(self, bucket: str, key: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self.s3.head_object, Bucket=bucket, Key=key)

    # Copy object (managed transfer will multipart if needed)
    async def copy_object(
        self,
        src_bucket: str,
        src_key: str,
        dst_bucket: str,
        dst_key: str,
        *,
        extra_args: Optional[Dict[str, Any]] = None,
    ) -> None:
        copy_source = {"Bucket": src_bucket, "Key": src_key}
        await asyncio.to_thread(
            self.s3.copy,
            copy_source, dst_bucket, dst_key,
            ExtraArgs=extra_args,
        )

    # Presigned GET URL
    async def generate_presigned_get_url(
        self, bucket: str, key: str, expires_in: int = 3600
    ) -> str:
        return await asyncio.to_thread(
            self.s3.generate_presigned_url,
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    # Presigned PUT URL (ensure client uses signature_version='s3v4' if needed)
    async def generate_presigned_put_url(
        self, bucket: str, key: str, expires_in: int = 3600
    ) -> str:
        return await asyncio.to_thread(
            self.s3.generate_presigned_url,
            "put_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
