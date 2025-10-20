from pydantic import BaseModel, Field, HttpUrl, model_validator, ConfigDict
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker
from pynamodb.models import Model
from pynamodb.attributes import UnicodeAttribute, ListAttribute, NumberAttribute, BooleanAttribute, JSONAttribute
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from datetime import datetime
import time
from .config import settings, harvester_settings
from .logging_config import get_logger
import json
from pathlib import Path

from typing import List, Optional, Literal

logger = get_logger(__name__)

class NewsArticle(BaseModel):
    title: str = Field(..., description="Article title.")
    body: str = Field(..., description="Main body text of the article, concatenated into one field.")
    url: str = Field(..., description="Canonical URL of the article.")
    published_at: Optional[str] = Field(None, description="UTC ISO 8601 like '2025-09-11T00:00:00Z'.")
    error: Optional[bool] = Field(None, description="Set only if extraction failed; otherwise omit.")
    keywords: Optional[List[str]] = None

class CrawlResult(BaseModel):
    """Result of crawling a single URL"""
    url: str
    success: bool
    article: Optional[NewsArticle] = None
    pdf_s3_key: Optional[str] = None
    json_s3_key: Optional[str] = None
    screenshot_s3_key: Optional[str] = None
    error: Optional[str] = None
    crawled_at: str

class MultipleCrawlRequest(BaseModel):
    """Request model for crawling multiple URLs"""
    urls: List[HttpUrl]
    save_pdf: bool = True
    save_screenshot: bool = False
    s3_prefix: Optional[str] = None

class SQSMessageRequest(BaseModel):
    body: str
    delay_seconds: Optional[int] = None
    message_attributes: Optional[Dict[str, Any]] = None

class CrawlRequest(BaseModel):
    type: Literal["crawl-single-url","crawl-rss"]
    url: HttpUrl
    id: str
    tags: List[str] | None = [ "global","news"]
    save_pdf: bool | None = True

class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None

# RSS Feed Models
class RSSFeedInfo(BaseModel):
    """RSS feed metadata information"""
    model_config = ConfigDict(extra='allow')

    title: str = ""
    description: str = ""
    link: str = ""
    language: str = ""
    updated: str = ""
    updated_parsed: Optional[tuple] = None
    generator: str = ""
    image: Dict[str, Any] = Field(default_factory=dict)
    rights: str = ""
    tags: List[Dict[str, Any]] = Field(default_factory=list)
    ttl: str = ""
    publisher: str = ""
    publisher_detail: Dict[str, Any] = Field(default_factory=dict)
    managing_editor: str = Field(default="", alias="managingEditor")
    web_master: str = Field(default="", alias="webMaster")
    category: str = ""
    cloud: Dict[str, Any] = Field(default_factory=dict)
    docs: str = ""
    text_input: Dict[str, Any] = Field(default_factory=dict, alias="textInput")
    skip_hours: List[str] = Field(default_factory=list, alias="skipHours")
    skip_days: List[str] = Field(default_factory=list, alias="skipDays")

class RSSAuthorDetail(BaseModel):
    """RSS author detail information"""
    model_config = ConfigDict(extra='allow')

    name: str = ""
    email: str = ""
    href: str = ""

class RSSEnclosure(BaseModel):
    """RSS enclosure information"""
    model_config = ConfigDict(extra='allow')

    href: str = ""
    type: str = ""
    length: str = ""

class RSSMediaContent(BaseModel):
    """RSS media content information"""
    model_config = ConfigDict(extra='allow')

    url: str = ""
    type: str = ""
    medium: str = ""
    width: Optional[str] = None
    height: Optional[str] = None
    filesize: Optional[str] = None

class RSSTag(BaseModel):
    """RSS tag/category information"""
    model_config = ConfigDict(extra='allow')

    term: str = ""
    scheme: Optional[str] = None
    label: Optional[str] = None

class RSSContent(BaseModel):
    """RSS content information"""
    model_config = ConfigDict(extra='allow')

    type: str = ""
    language: Optional[str] = None
    base: Optional[str] = None
    value: str = ""

class RSSItem(BaseModel):
    """Individual RSS feed item with all possible fields"""
    model_config = ConfigDict(extra='allow')

    # Core fields
    title: str = ""
    link: str = ""
    description: str = ""
    summary: str = ""
    content: List[RSSContent] = Field(default_factory=list)

    # Date/time fields
    published: str = ""
    published_parsed: Optional[tuple] = None
    published_iso: Optional[str] = None
    updated: str = ""
    updated_parsed: Optional[tuple] = None
    updated_iso: Optional[str] = None

    # Author information
    author: str = ""
    author_detail: Optional[RSSAuthorDetail] = None
    authors: List[RSSAuthorDetail] = Field(default_factory=list)

    # Categorization
    tags: List[RSSTag] = Field(default_factory=list)
    category: str = ""
    categories: List[Dict[str, Any]] = Field(default_factory=list)

    # Media and enclosures
    enclosures: List[RSSEnclosure] = Field(default_factory=list)
    media_content: List[RSSMediaContent] = Field(default_factory=list)
    media_thumbnail: List[Dict[str, Any]] = Field(default_factory=list)

    # Identifiers
    id: str = ""
    guid: str = ""

    # Comments and interaction
    comments: str = ""
    wfw_commentrss: str = ""

    # Dublin Core metadata
    dc_creator: str = ""
    dc_date: str = ""
    dc_subject: str = ""
    dc_rights: str = ""

    # Source information
    source: Dict[str, Any] = Field(default_factory=dict)

    # Custom namespaces
    slash_comments: str = ""
    feedburner_origlink: str = ""

class RSSFeedResult(BaseModel):
    """Complete RSS feed parsing result"""
    model_config = ConfigDict(extra='allow')

    feed_url: str
    feed_info: RSSFeedInfo
    items: List[RSSItem]
    total_items: int
    parsed_at: str
    status: Literal["success", "error"]
    error: Optional[str] = None
    config: Optional[Dict[str, Any]] = None

class RSSFeedConfig(BaseModel):
    """RSS feed configuration from harvester config"""
    model_config = ConfigDict(extra='allow')

    type: Literal["crawl_rss"]
    id: str
    tags: List[str]
    feed_url: HttpUrl
    max_items: Optional[int] = Field(default=None, ge=1)
    only_new: Optional[bool] = None
    item_link_field: Optional[str] = "link"
    allow_patterns: Optional[List[str]] = None
    save_pdf: Optional[bool] = True

class RSSFilterCriteria(BaseModel):
    """Criteria for filtering RSS items"""
    model_config = ConfigDict(extra='allow')

    title_contains: Optional[str] = None
    published_after: Optional[datetime] = None
    published_before: Optional[datetime] = None
    has_content: bool = False
    author_contains: Optional[str] = None
    tags_contain: Optional[List[str]] = None



# Harvester Configuration Models

class HarvesterConfigMetadata(BaseModel):
    """Top-level harvester configuration metadata"""
    model_config = ConfigDict(extra='forbid')

    version: str
    description: str
    user_agent: str
    respect_robots_txt: bool = True
    concurrency: int = Field(default=4, ge=1, le=20)
    rate_limit_per_host: int = Field(default=2, ge=1, le=10)
    timeout_seconds: int = Field(default=15, ge=5, le=60)

class CrawlRSSTask(BaseModel):
    """RSS feed crawling task configuration"""
    model_config = ConfigDict(extra='forbid')

    type: Literal["crawl_rss"]
    id: str = Field(..., min_length=1, max_length=100)
    tags: List[str] = Field(..., min_length=1)
    feed_url: HttpUrl
    max_items: Optional[int] = Field(default=None, ge=1, le=1000)
    only_new: Optional[bool] = None
    item_link_field: Optional[str] = Field(default="link")
    allow_patterns: Optional[List[str]] = None
    save_pdf: Optional[bool] = True

class CrawlSiteTask(BaseModel):
    """Website crawling task configuration"""
    model_config = ConfigDict(extra='forbid')

    type: Literal["crawl_site"]
    id: str = Field(..., min_length=1, max_length=100)
    tags: List[str] = Field(..., min_length=1)
    start_url: HttpUrl
    max_depth: Optional[int] = Field(default=2, ge=0, le=10)
    same_origin_only: Optional[bool] = True
    allowed_domains: Optional[List[str]] = None
    allow_patterns: Optional[List[str]] = None
    deny_patterns: Optional[List[str]] = None
    capture_outgoing_links: Optional[bool] = None
    save_pdf: Optional[bool] = True

class CrawlSitemapTask(BaseModel):
    """Sitemap-based crawling task configuration"""
    model_config = ConfigDict(extra='forbid')

    type: Literal["crawl_sitemap"]
    id: str = Field(..., min_length=1, max_length=100)
    tags: List[str] = Field(..., min_length=1)
    sitemap_url: HttpUrl
    max_depth: Optional[int] = Field(default=2, ge=0, le=10)
    same_origin_only: Optional[bool] = True
    allowed_domains: Optional[List[str]] = None
    allow_patterns: Optional[List[str]] = None
    deny_patterns: Optional[List[str]] = None
    capture_outgoing_links: Optional[bool] = None
    save_pdf: Optional[bool] = True

# Union type for all task types
HarvesterTask = Union[CrawlRSSTask, CrawlSiteTask, CrawlSitemapTask]

class HarvesterConfig(BaseModel):
    """Complete harvester configuration with metadata and tasks"""
    model_config = ConfigDict(extra='forbid')

    version: str
    description: str
    user_agent: str
    respect_robots_txt: bool = True
    concurrency: int = Field(default=4, ge=1, le=20)
    rate_limit_per_host: int = Field(default=2, ge=1, le=10)
    timeout_seconds: int = Field(default=15, ge=5, le=60)
    tasks: List[HarvesterTask] = Field(..., min_length=1)

    @model_validator(mode='after')
    def validate_unique_task_ids(self):
        """Ensure all task IDs are unique"""
        task_ids = [task.id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Task IDs must be unique")
        return self

    def get_tasks_by_type(self, task_type: str) -> List[HarvesterTask]:
        """Get all tasks of a specific type"""
        return [task for task in self.tasks if task.type == task_type]

    def get_task_by_id(self, task_id: str) -> Optional[HarvesterTask]:
        """Get a specific task by ID"""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

# PynamoDB Model for DynamoDB Storage

class HarvesterConfigTask(Model):
    """PynamoDB model for storing harvester configuration tasks in DynamoDB"""

    class Meta:
        # Use the harvester_config_table from settings
        table_name = harvester_settings.harvester_config_table or "harvester-config-tasks"
        region = harvester_settings.aws_region or "eu-central-1"
        # Add billing mode for on-demand pricing
        billing_mode = 'PAY_PER_REQUEST'

    # Primary key
    task_id = UnicodeAttribute(hash_key=True)

    # Task configuration
    task_type = UnicodeAttribute()
    tags = ListAttribute(of=UnicodeAttribute)

    # Common fields (stored as JSON for flexibility)
    config_data = JSONAttribute()

    # Metadata
    created_at = UnicodeAttribute()
    updated_at = UnicodeAttribute()

    # Configuration metadata (denormalized for easy querying)
    version = UnicodeAttribute()

    @classmethod
    def from_pydantic_task(cls, task: HarvesterTask, config_version: str) -> 'HarvesterConfigTask':
        """Create a PynamoDB model instance from a Pydantic task model"""
        now = datetime.utcnow().isoformat()

        return cls(
            task_id=task.id,
            task_type=task.type,
            tags=task.tags,
            config_data=task.model_dump(mode="json"),  # Use mode="json" to make HttpUrl JSON serializable
            created_at=now,
            updated_at=now,
            version=config_version
        )

    def to_pydantic_task(self) -> HarvesterTask:
        """Convert PynamoDB model back to Pydantic task model"""
        config_data = dict(self.config_data)
        task_type = config_data.get('type')

        if task_type == 'crawl_rss':
            return CrawlRSSTask.model_validate(config_data)
        elif task_type == 'crawl_site':
            return CrawlSiteTask.model_validate(config_data)
        elif task_type == 'crawl_sitemap':
            return CrawlSitemapTask.model_validate(config_data)
        else:
            raise ValueError(f"Unknown task type: {task_type}")

# PynamoDB Model for storing processed RSS items
class ProcessedRSSItem(Model):
    """PynamoDB model for storing processed RSS items in DynamoDB"""

    class Meta:
        # Use a separate table for processed RSS items
        table_name = harvester_settings.dynamodb_rss_processed_table_name
        region = harvester_settings.aws_region
        # Add billing mode for on-demand pricing
        billing_mode = 'PAY_PER_REQUEST'

    # Primary key - task_id (hash) and url_hash (range)
    task_id = UnicodeAttribute(hash_key=True)
    url_hash = UnicodeAttribute(range_key=True)

    # URL and metadata
    url = UnicodeAttribute()
    processed_at = UnicodeAttribute()

    # TTL for automatic expiration (30 days by default)
    ttl = NumberAttribute(null=True, default=lambda: int(time.time()) + 30 * 24 * 3600)

# PynamoDB Model for storing crawled websites
class CrawledWebsite(Model):
    """PynamoDB model for storing crawled websites in DynamoDB"""

    class Meta:
        # Use the dynamodb_state_table_name from settings
        table_name = harvester_settings.dynamodb_state_table_name or "harvester-state"
        region = harvester_settings.aws_region or "eu-central-1"
        # Add billing mode for on-demand pricing
        billing_mode = 'PAY_PER_REQUEST'

    # Primary key - URL hash
    url_hash = UnicodeAttribute(hash_key=True)

    # URL and metadata
    url = UnicodeAttribute()
    title = UnicodeAttribute(null=True)
    crawled_at = UnicodeAttribute()
    published_at = UnicodeAttribute(null=True)

    # Content information
    has_content = BooleanAttribute(default=False)
    content_length = NumberAttribute(null=True)
    keywords = ListAttribute(of=UnicodeAttribute, null=True)

    # Storage locations - local paths
    json_path = UnicodeAttribute(null=True)
    text_path = UnicodeAttribute(null=True)
    pdf_path = UnicodeAttribute(null=True)

    # Storage locations - S3 paths
    s3_json_path = UnicodeAttribute(null=True)
    s3_text_path = UnicodeAttribute(null=True)
    s3_pdf_path = UnicodeAttribute(null=True)

    # Processing status
    success = BooleanAttribute(default=True)
    error = UnicodeAttribute(null=True)

    # TTL for automatic expiration
    ttl = NumberAttribute(null=True)

    @classmethod
    def from_crawl_result(cls, url: str, url_hash: str, article: Dict[str, Any],
                         save_paths: Dict[str, str], success: bool = True,
                         error: str = None, ttl_seconds: int = None):
        """Create a PynamoDB model instance from crawl result data"""
        now = datetime.utcnow().isoformat()

        # Calculate TTL if provided
        ttl_value = None
        if ttl_seconds:
            import time
            ttl_value = int(time.time()) + ttl_seconds

        return cls(
            url_hash=url_hash,
            url=url,
            title=article.get("title") if article else None,
            crawled_at=now,
            published_at=article.get("published_at") if article else None,
            has_content=bool(article and article.get("body")),
            content_length=len(article.get("body", "")) if article else 0,
            keywords=article.get("keywords", []) if article else None,
            # Local paths
            json_path=save_paths.get("json"),
            text_path=save_paths.get("text"),
            pdf_path=save_paths.get("pdf"),
            # S3 paths
            s3_json_path=save_paths.get("s3_json"),
            s3_text_path=save_paths.get("s3_text"),
            s3_pdf_path=save_paths.get("s3_pdf"),
            success=success,
            error=error,
            ttl=ttl_value
        )
