import os
import asyncio
import time
import boto3
from botocore.config import Config
from contextlib import asynccontextmanager

from fastapi.responses import JSONResponse
from fastapi import FastAPI

from core.config import harvester_settings
from core.logging_config import get_logger
from core.models import ErrorResponse, CrawledWebsite
from core.s3_utils import AsyncBoto3S3
from core.sqs_utils import AsyncBoto3SQS

from .api.endpoints import router
from .message_processor import HarvesterSQSConsumer
from .bedrock_token import BedrockToken, set_app
from .rss_processor import process_rss_feeds, schedule_rss_feed_processing

# Get logger with centralized configuration
logger = get_logger(__name__)

# Helpers
s3_helper: AsyncBoto3S3
sqs_helper: AsyncBoto3SQS
consumer: HarvesterSQSConsumer
bedrock_token: BedrockToken
rss_task: asyncio.Task = None

# DynamoDB task tracking
def ddb_table():
    dynamodb_table = boto3.resource("dynamodb").Table(harvester_settings.dynamodb_state_table_name)
    return dynamodb_table

def now_epoch() -> int:
    return int(time.time())

def ttl_after(seconds: int) -> int:
    return now_epoch() + seconds

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    global s3_helper, sqs_helper, consumer, harvester_sqs_queue_url, verifier_sqs_queue_url, bedrock_token, rss_task

    s3_client = boto3.client(
        "s3",
        region_name=harvester_settings.aws_region,
        # Signature v4 helps with presigned PUT URLs
        config=Config(signature_version="s3v4"),
    )

    s3_helper = AsyncBoto3S3(s3_client)

    sqs_client = boto3.client("sqs", region_name=harvester_settings.sqs_aws_region)

    # get queue names based on aws_region and sqs_aws_region env vars
    harvester_sqs_queue_url = sqs_client.get_queue_url(QueueName = harvester_settings.harvester_sqs_queue_name)['QueueUrl']

    sqs_helper = AsyncBoto3SQS(sqs_client)
    consumer = HarvesterSQSConsumer(
        helper=sqs_helper,                                             # sqs helper asyncBoto3SQS
        queue_url=harvester_sqs_queue_url,                             # sqs queue url for consumer
        concurrency=5,                                                 # how many messages to process concurrently
        wait_time=harvester_settings.sqs_wait_time,                    # SQS long-poll seconds (max 20)
        max_number=10,                                                 # up to 10 per receive
        visibility_timeout=harvester_settings.sqs_visibility_timeout,  # match queue or processing need
        heartbeat_every=30,                                            # extend visibility while processing
        # No need for process_func - it's built into the class!
    )

    logger.info("Starting News Harvester Agent API..")
    logger.info(f"AWS Region: {harvester_settings.aws_region}")
    logger.info(f"Bedrock Model: {harvester_settings.bedrock_model_id}")
    logger.info(f"SQS AWS Region: {harvester_settings.sqs_aws_region}")
    logger.info(f"Harvester SQS Queue: {harvester_settings.harvester_sqs_queue_name}")
    logger.info(f"Debug Mode: {harvester_settings.debug}")

    bedrock_token = BedrockToken()

    # Stash shared state for endpoints
    app.state.sqs_helper = sqs_helper
    app.state.sqs_consumer = consumer
    app.state.queue_url = harvester_sqs_queue_url
    app.state.bedrock_token = bedrock_token
    app.state.s3_helper = s3_helper


    # start sqs consumer task
    await consumer.start()
    # start bedrock token task
    set_app(app)
    await bedrock_token.start()

    app.state.bedrock_api_token = await bedrock_token.get_token()

    # Start RSS feed processing task
    logger.info("Starting RSS feed processing task")
    rss_task = asyncio.create_task(
        schedule_rss_feed_processing(
            sqs_helper=sqs_helper,
            queue_url=harvester_sqs_queue_url
            # No need to specify interval_seconds, it will use the configured value
        )
    )

    try:
        yield
    finally:
        # stop the sqs consumer task
        await consumer.stop()
        # stop the bedrock token task
        await bedrock_token.stop()
        # stop the RSS processing task if it exists
        if rss_task and not rss_task.done():
            logger.info("Stopping RSS feed processing task")
            rss_task.cancel()
            try:
                await rss_task
            except asyncio.CancelledError:
                logger.info("RSS feed processing task cancelled")

    # Shutdown
    logger.info("Shutting down Harvester Agent API...")

# FastAPI app
app = FastAPI(
    title="News Harvester API",
    version="1.0.0",
    description="API for Crawling URLs, either RSS, Single URLs and adding to AWS S3 and AWS DynamoDB for processing.",
    lifespan=lifespan
)

# Include API routes
app.include_router(router, prefix="/api/v1")

@app.get("/")
async def root():
    """Root endpoint."""
    return JSONResponse(content={"message": "News Harvester API","version": "1.0.0","status": "running"})

@app.get("/health")
async def health():
    """Health check endpoint for Lambda Web Adapter."""
    return JSONResponse(content={"status": "healthy"})

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal Server Error",
            message="An unexpected error occurred",
            details={"type": type(exc).__name__}
        ).dict()
    )

if __name__ == "__main__":
    import uvicorn

    # Disable reload in Docker to prevent duplicate initialization
    # Volume mounts + auto-reload can cause issues with lifespan managers
    import os
    is_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER', False)
    is_lambda = os.environ.get('AWS_LAMBDA_FUNCTION_NAME') is not None

    # Use PORT environment variable for Lambda Web Adapter compatibility
    port = int(os.environ.get('PORT', harvester_settings.api_port))

    uvicorn.run(
        "harvester.app.main:app",
        host=harvester_settings.api_host,
        port=port,
        reload=harvester_settings.debug and not is_docker and not is_lambda,  # Disable reload in Docker and Lambda
        log_level="info"
    )
