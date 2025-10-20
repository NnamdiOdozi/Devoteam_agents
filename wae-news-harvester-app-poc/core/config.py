import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class SharedSettings(BaseSettings):
    # AWS Configuration
    aws_region: str | None = "eu-central-1"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None

    # API Configuration
    api_host: str | None = "0.0.0.0"
    api_port: int | None = 8000
    debug: bool | None = True

    # Logging Configuration
    log_level: str | None = "INFO"

    # SQS
    sqs_wait_time: int | None = 20 # long poll - to avoid tight loop, upto 20 seconds between message detection
    sqs_visibility_timeout: int | None = 120 # sqs visibility timeout
    sqs_aws_region: str | None = aws_region

    # AWS Bedrock Configuration
    bedrock_token_expiry_seconds: int | None = 43200 # 12 hours
    bedrock_aws_region: str | None = aws_region # default to same as everything else
    bedrock_model_id: str | None = "eu.anthropic.claude-3-7-sonnet-20250219-v1:0"
    bedrock_model_temperature: float | None = 0.1 # Lower temperature for more focused responses
    bedrock_model_max_tokens: int | None = 4096 # max tokens
    bedrock_model_top_k: int | None = 20 # number results

    # DynamoDB
    dynamodb_state_table_name: str | None = None # DynamoDB table used by all 3 agents/services
    dynamodb_rss_processed_table_name : str | None = None # rss processed articles table.
    dynamodb_task_ttl_secs: int | None = 24 * 3600 # expire items after 24h

    model_config = SettingsConfigDict( extra = None, env_file = ".env", case_sensitive = False )

class HarvesterSettings(SharedSettings):
    crawl_save_location: str | None = "crawled"
    harvester_browser_profile: str | None = "/tmp/browser_profile"
    harvester_config_table: str | None = None # configuration table for sites to crawl
    bedrock_model_id: str | None = "eu.amazon.nova-pro-v1:0"
    harvester_sqs_queue_name: str # harvester ingest queue
    s3_bucket_name: str # s3 bucket

    # RSS feed processing configuration
    rss_processing_interval_seconds: int | None = 600  # Check RSS feeds every 10 minutes by default
    rss_track_processed_urls: bool | None = True  # Track processed URLs to avoid duplicates

settings = SharedSettings()
harvester_settings = HarvesterSettings()
