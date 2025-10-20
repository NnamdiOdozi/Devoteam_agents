import os
import json
import asyncio
import hashlib
from datetime import date, datetime, time, timedelta
from pathlib import Path
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any, Tuple
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
    LLMConfig,
)
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai import LLMExtractionStrategy  # or from crawl4ai.extraction_strategy import LLMExtractionStrategy
from typing import Annotated
from core.models import NewsArticle
from fastapi import Request
from core.config import harvester_settings
from core.s3_utils import AsyncBoto3S3
from .dynamodb import store_crawled_website_in_dynamodb
from core.logging_config import get_logger
from .bedrock_token import BedrockToken, get_app
logger = get_logger(__name__)


def get_bedrock_token() -> str:
    """
    Get the Bedrock token from the app object
    """
    app = get_app()
    token = app.state.bedrock_api_token
    return token

# Upload file to S3
async def upload_file_to_s3(
    s3_helper: AsyncBoto3S3,
    file_path: Path,
    s3_key: str,
    content_type: str = None
) -> str:
    """
    Upload a file to S3.

    Args:
        s3_helper: AsyncBoto3S3 helper
        file_path: Path to the file to upload
        s3_key: S3 key to upload to
        content_type: Content type of the file (optional)

    Returns:
        str: S3 key where the file was uploaded
    """
    from core.logging_config import get_logger
    logger = get_logger(__name__)

    try:
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        await s3_helper.upload_file(
            bucket=harvester_settings.s3_bucket_name,
            key=s3_key,
            filename=str(file_path),
            extra_args=extra_args
        )
        logger.debug(f"Uploaded {file_path} to s3://{harvester_settings.s3_bucket_name}/{s3_key}")
        return s3_key
    except Exception as e:
        logger.error(f"Error uploading {file_path} to S3: {str(e)}", exc_info=True)
        return None

# Get S3 helper from the main application
async def get_s3_helper(request: Request = None):
    """
    Get the S3 helper from either a request object or create a new one.

    Args:
        request: FastAPI request object (optional)

    Returns:
        AsyncBoto3S3: S3 helper
    """
    from core.logging_config import get_logger
    logger = get_logger(__name__)

    try:
        if request and hasattr(request.app.state, "s3_helper"):
            logger.debug("Getting S3 helper from request app state")
            return request.app.state.s3_helper
        else:
            # Create a new S3 helper
            logger.debug("Creating new S3 helper")
            from boto3 import client
            from botocore.config import Config
            s3_client = client(
                "s3",
                region_name=harvester_settings.aws_region,
                # Signature v4 helps with presigned PUT URLs
                config=Config(signature_version="s3v4"),
            )
            return AsyncBoto3S3(s3_client)
    except Exception as e:
        logger.error(f"Error getting S3 helper: {str(e)}", exc_info=True)
        raise

async def crawl_urls(urls: List[str], save_location: str = None, s3_helper: AsyncBoto3S3 = None, request: Request = None):
    """
    Crawl multiple URLs and extract article content using LLM

    Args:
        urls: List of URLs to crawl
        save_location: Base directory to save results (optional)
        s3_helper: AsyncBoto3S3 helper (optional)
        request: FastAPI request object (optional)

    Returns:
        List of paths where files were saved
    """
    if isinstance(urls, str):
        # Handle single URL passed as string
        urls = [urls]

    # Get S3 helper if not provided
    if s3_helper is None:
        s3_helper = await get_s3_helper(request)

    md_generator = DefaultMarkdownGenerator( options={ "ignore_links": True, } )



    # Common extraction instruction
    extraction_instruction = """
        Extract the main article content, return a concise title and the primary article body as plain text.
        Usually the main article is within a single div container and may have sub headings included.
        Exclude navigation, ads, cookie banners, any other parts of the page that dont seem like they are the main article and footers..
        If you can find the article publication date, include this field as published_at, if this cannot be found, user the current date and time.
        Do not include any Unicode characters, special symbols, escape sequences, escaping of quotes or extended ASCII characters in your output.
        Stick to the basic Latin alphabet (A-Z, a-z), numbers (0-9), and common punctuation marks (.,!?-_:;()'").
        Also generate a list of keywords from the main article content and populate these in the keywords field of the model.
    """
    bedrock_api_token = get_bedrock_token()

    # Normal case - we have a valid token
    llm_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider=f"bedrock/{harvester_settings.bedrock_model_id}",
            api_token=bedrock_api_token,
        ),
        schema=NewsArticle.model_json_schema(), # JSON schema shape for output
        extraction_type="schema",
        instruction=extraction_instruction,
        input_format="markdown",
        apply_chunking=False,
        extra_args={"temperature": 0.0, "max_tokens": 4096},
    )

    run_config = CrawlerRunConfig(
        wait_until="domcontentloaded",
        exclude_external_links=True,  # drop off-domain links from result.links
        exclude_social_media_links=True,  # optional: strip known social platforms
        markdown_generator=md_generator,
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=llm_strategy,
        pdf=True,                                        # request printable PDF capture
    )

    saved_paths = []
    async with AsyncWebCrawler(config=BrowserConfig(
            headless=True,
            use_managed_browser=True,
            browser_type="chromium",
            user_data_dir=harvester_settings.harvester_browser_profile)) as crawler:

        # Use arun_many for multiple URLs
        results = await crawler.arun_many(urls=urls, config=run_config, magic=True)

        # Process each result
        for url, result in zip(urls, results):
            if not result.success:
                error_msg = f"Failed to crawl {url}: {result.error_message}"
                logger.error(error_msg)
                # Propagate the error to trigger retry logic
                raise Exception(error_msg)

            # Create directory structure based on date and URL hash
            today = datetime.now()
            url_hash = hashlib.md5(url.encode()).hexdigest()[-8:]  # Last 8 chars of MD5 hash

            # Build path: /year/month/day/md5ofURL(last 8 characters)/
            relative_path = f"{today.year}/{today.month:02d}/{today.day:02d}/{url_hash}"

            # Use save_location if provided, otherwise use current directory
            if save_location:
                save_dir = Path(save_location) / relative_path
            else:
                save_dir = Path(relative_path)

            # Create directories if they don't exist
            save_dir.mkdir(parents=True, exist_ok=True)

            try:
                # Save LLM-extracted JSON
                article = None
                success = True
                error_msg = None
                save_paths = {}
                s3_paths = {}

                try:
                    extracted_data = json.loads(result.extracted_content)

                    # Log the structure of the extracted data for debugging
                    print(f"Extracted data type: {type(extracted_data)}")
                    logger.debug(f"Raw extracted content preview: {result.extracted_content[:200]}...")

                    # Handle both array and object formats
                    if isinstance(extracted_data, list) and len(extracted_data) > 0:
                        article = extracted_data[0]  # Get first item if it's an array
                        print(f"Extracted data is an array with {len(extracted_data)} items")
                    else:
                        article = extracted_data  # Use directly if it's already an object
                        print("Extracted data is a direct object")

                    # Save article JSON locally
                    json_path = save_dir / "article.json"
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(article, f, ensure_ascii=False, indent=2)
                    save_paths["json"] = str(json_path)

                    # Upload JSON to S3
                    if harvester_settings.s3_bucket_name:
                        s3_json_key = f"{save_location}/{relative_path}/article.json"
                        s3_json_path = await upload_file_to_s3(
                            s3_helper,
                            json_path,
                            s3_json_key,
                            "application/json"
                        )
                        if s3_json_path:
                            s3_paths["json"] = s3_json_path

                    # Save article body as plain text
                    txt_path = save_dir / "article.txt"
                    with open(txt_path, "w", encoding="utf-8") as f:
                        if "body" in article and article["body"]:
                            body_content = article["body"]
                            # Debug: Print first 100 chars of content
                            logger.debug(f"Body content preview: {body_content[:100]}...")
                            logger.debug(f"Body content type: {type(body_content)}")

                            # Ensure body_content is a string
                            if not isinstance(body_content, str):
                                body_content = str(body_content)

                            # Write content to file
                            f.write(body_content)
                            f.flush()  # Ensure content is written to disk

                            # Verify file was written correctly
                            logger.debug(f"Saved article body ({len(body_content)} characters) to {txt_path}")
                            save_paths["text"] = str(txt_path)

                            # Upload text to S3
                            if harvester_settings.s3_bucket_name:
                                s3_txt_key = f"{save_location}/{relative_path}/article.txt"
                                s3_txt_path = await upload_file_to_s3(
                                    s3_helper,
                                    txt_path,
                                    s3_txt_key,
                                    "text/plain"
                                )
                                if s3_txt_path:
                                    s3_paths["text"] = s3_txt_path
                        else:
                            print(f"Warning: No body content found for {url}")
                            print(f"Available fields in article: {list(article.keys())}")
                except Exception as e:
                    error_msg = f"Error processing extracted content: {str(e)}"
                    print(f"{error_msg} for {url}")
                    success = False
                    # Save the raw extracted content for debugging
                    raw_path = save_dir / "raw_extracted.txt"
                    with open(raw_path, "w", encoding="utf-8") as f:
                        f.write(result.extracted_content)
                    print(f"Saved raw extracted content to {raw_path}")

                # Save printable PDF capture
                if result.pdf:
                    pdf_path = save_dir / "article.pdf"
                    with open(pdf_path, "wb") as f:
                        f.write(result.pdf)
                    save_paths["pdf"] = str(pdf_path)

                    # Upload PDF to S3
                    if harvester_settings.s3_bucket_name:
                        s3_pdf_key = f"{save_location}/{relative_path}/article.pdf"
                        s3_pdf_path = await upload_file_to_s3(
                            s3_helper,
                            pdf_path,
                            s3_pdf_key,
                            "application/pdf"
                        )
                        if s3_pdf_path:
                            s3_paths["pdf"] = s3_pdf_path

                print(f"Saved files for {url} to {save_dir}")
                if s3_paths:
                    logger.debug(f"Uploaded files to S3: {', '.join(s3_paths.keys())}")
                saved_paths.append(str(save_dir))

                # Store in DynamoDB if table name is configured
                if harvester_settings.dynamodb_state_table_name:
                    # Combine local and S3 paths
                    all_paths = {**save_paths}
                    # Add S3 paths with s3:// prefix
                    for key, path in s3_paths.items():
                        all_paths[f"s3_{key}"] = f"s3://{harvester_settings.s3_bucket_name}/{path}"

                    # Store the crawled website in DynamoDB
                    await store_crawled_website_in_dynamodb(
                        url=url,
                        url_hash=url_hash,
                        article=article,
                        save_paths=all_paths,
                        success=success,
                        error=error_msg
                    )
            except Exception as e:
                print(f"Error processing result for {url}: {str(e)}")

        return saved_paths

async def crawl_url_for_response(url: str, s3_helper: AsyncBoto3S3 = None, request: Request = None) -> Dict[str, Any]:
    """
    Crawl a single URL and return the article content as JSON response

    Args:
        url: URL to crawl
        s3_helper: AsyncBoto3S3 helper (optional, not used in response mode)
        request: FastAPI request object (optional)

    Returns:
        Dict containing the article data (same format as article.json)
    """
    # Note: S3 helper not needed for response-only mode, but keeping parameter for consistency

    md_generator = DefaultMarkdownGenerator( options={ "ignore_links": True, } )

    # Common extraction instruction
    extraction_instruction = """
        Extract the main article content, return a concise title and the primary article body as plain text.
        Usually the main article is within a single div container and may have sub headings included.
        Exclude navigation, ads, cookie banners, any other parts of the page that dont seem like they are the main article and footers..
        If you can find the article publication date, include this field as published_at, if this cannot be found, user the current date and time.
        Do not include any Unicode characters, special symbols, escape sequences, escaping of quotes or extended ASCII characters in your output.
        Stick to the basic Latin alphabet (A-Z, a-z), numbers (0-9), and common punctuation marks (.,!?-_:;()'").
        Also generate a list of keywords from the main article content and populate these in the keywords field of the model.
    """
    bedrock_api_token = get_bedrock_token()

    # Normal case - we have a valid token
    llm_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider=f"bedrock/{harvester_settings.bedrock_model_id}",
            api_token=bedrock_api_token,
        ),
        schema=NewsArticle.model_json_schema(), # JSON schema shape for output
        extraction_type="schema",
        instruction=extraction_instruction,
        input_format="markdown",
        apply_chunking=False,
        extra_args={"temperature": 0.0, "max_tokens": 4096},
    )

    run_config = CrawlerRunConfig(
        wait_until="domcontentloaded",
        exclude_external_links=True,  # drop off-domain links from result.links
        exclude_social_media_links=True,  # optional: strip known social platforms
        markdown_generator=md_generator,
        cache_mode=CacheMode.BYPASS,
        extraction_strategy=llm_strategy,
        pdf=False,  # Don't need PDF for response-only mode
    )

    async with AsyncWebCrawler(config=BrowserConfig(
            headless=True,
            use_managed_browser=True,
            browser_type="chromium",
            user_data_dir=harvester_settings.harvester_browser_profile)) as crawler:

        # Crawl single URL
        result = await crawler.arun(url=url, config=run_config, magic=True)

        if not result.success:
            error_msg = f"Failed to crawl {url}: {result.error_message}"
            logger.error(error_msg)
            raise Exception(error_msg)

        try:
            extracted_data = json.loads(result.extracted_content)

            # Log the structure of the extracted data for debugging
            logger.debug(f"Extracted data type: {type(extracted_data)}")
            logger.debug(f"Raw extracted content preview: {result.extracted_content[:200]}...")

            # Handle both array and object formats
            if isinstance(extracted_data, list) and len(extracted_data) > 0:
                article = extracted_data[0]  # Get first item if it's an array
                logger.debug(f"Extracted data is an array with {len(extracted_data)} items")
            else:
                article = extracted_data  # Use directly if it's already an object
                logger.debug("Extracted data is a direct object")

            # Ensure the article has the required URL field
            if "url" not in article or not article["url"]:
                article["url"] = url

            logger.info(f"Successfully extracted article from {url}")
            return article

        except Exception as e:
            error_msg = f"Error processing extracted content: {str(e)}"
            logger.error(f"{error_msg} for {url}")
            raise Exception(error_msg)
