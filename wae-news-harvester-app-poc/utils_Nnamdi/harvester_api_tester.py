import uuid
from datetime import datetime
from pathlib import Path

import requests
import feedparser

BASE_URL = "http://13.53.235.49:8010"

URLS_TO_TEST = [
    "https://getjuniper.co.uk",
    "https://fertifa.com",
    "https://fertilitynetworkuk.org",
    "https://hertilityhealth.com",
    "https://resolve.org",
    "https://fertilitymattersatwork.com",
    "https://bournhall.co.uk",
    "https://unfpa.org",
    "https://gaiafamily.com",
]

# Verified RSS feeds for news sources
RSS_FEEDS = {
    "BBC News – Health": "https://feeds.bbci.co.uk/news/health/rss.xml",
    "The Guardian – Society/Health": "https://www.theguardian.com/society/health/rss",
    "The Guardian – Health & Wellbeing": "https://www.theguardian.com/lifeandstyle/health-and-wellbeing/rss",
    "Healthwatch England – News": "https://www.healthwatch.co.uk/taxonomy/term/85/feed",
}

LOG_FILE = Path(__file__).resolve().with_name("harvester_test.log")


def log(message: str):
    timestamp = datetime.now().isoformat(timespec="seconds")
    line = f"[{timestamp}] {message}"
    print(line)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        # Avoid blocking the test flow on logging failures.
        pass

def health_check():
    url = f"{BASE_URL}/health"
    log(f"\n[HEALTH] GET {url}")
    resp = requests.get(url, timeout=20)
    log(f"Status: {resp.status_code}")
    try:
        log(f"Body: {resp.json()}")
    except Exception:
        log(f"Body (text): {resp.text[:400]}")


def build_crawl_request(url: str, tags_extra=None):
    tags = ["policy-pulse-test"]
    if tags_extra:
        tags.extend(tags_extra)
    return {
        "type": "crawl-single-url",
        "url": url,
        "id": f"test-{uuid.uuid4()}",
        "tags": tags,
        "save_pdf": True,
    }


def enqueue_crawl(url: str, tags_extra=None):
    endpoint = f"{BASE_URL}/api/v1/crawl/url"
    payload = build_crawl_request(url, tags_extra=tags_extra)

    log(f"\n[ENQUEUE] POST {endpoint}")
    log(f"Request body: {payload}")

    resp = requests.post(endpoint, json=payload, timeout=30)
    log(f"Status: {resp.status_code}")
    try:
        log(f"Response JSON: {resp.json()}")
    except Exception:
        log(f"Response text: {resp.text[:400]}")


def call_url_response(url: str, tags_extra=None):
    endpoint = f"{BASE_URL}/api/v1/crawl/url_response"
    payload = build_crawl_request(url, tags_extra=tags_extra)

    log(f"\n[URL_RESPONSE] POST {endpoint}")
    log(f"Request body: {payload}")

    try:
        # shorter timeout so you are not stuck for 2 minutes on a bad URL
        resp = requests.post(endpoint, json=payload, timeout=40)
    except requests.exceptions.ReadTimeout:
        log("Result: TIMEOUT (no response within 40s)")
        return

    log(f"Status: {resp.status_code}")
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            log(f"Response JSON: {resp.json()}")
        except Exception:
            log(f"Response text (first 400 chars): {resp.text[:400]}")
    else:
        log(f"Response text (first 400 chars): {resp.text[:400]}")


def configure_rss_feed(feed_name: str, feed_url: str, tags_extra=None, max_items=None):
    """
    Configure an RSS feed for monitoring by the harvester.
    The harvester will check this feed every 10 minutes and enqueue new articles.

    Args:
        feed_name: Human-readable identifier for this feed
        feed_url: URL of the RSS feed XML
        tags_extra: Additional tags to apply to articles from this feed
        max_items: Maximum number of items to fetch per RSS check (None for all)
    """
    endpoint = f"{BASE_URL}/api/v1/crawl/rss"

    # Build tags
    tags = ["policy-pulse-test", "rss"]
    if tags_extra:
        tags.extend(tags_extra)

    # Create a URL-safe ID from the feed name
    feed_id = f"test-rss-{feed_name.lower().replace(' ', '-').replace('–', '-')}-{uuid.uuid4().hex[:8]}"

    payload = {
        "type": "crawl_rss",
        "id": feed_id,
        "tags": tags,
        "feed_url": feed_url,
        "max_items": max_items,
        "save_pdf": True
    }

    log(f"\n[CONFIGURE_RSS] POST {endpoint}")
    log(f"Feed Name: {feed_name}")
    log(f"Request body: {payload}")

    try:
        resp = requests.post(endpoint, json=payload, timeout=30)
        log(f"Status: {resp.status_code}")
        try:
            log(f"Response JSON: {resp.json()}")
        except Exception:
            log(f"Response text: {resp.text[:400]}")
    except Exception as e:
        log(f"Error configuring RSS feed: {e}")


def test_rss_feed_immediate(feed_name: str, feed_url: str, tags_extra=None, max_items=5):
    """
    Immediately test an RSS feed by parsing it and enqueuing article URLs.
    This bypasses the 10-minute scheduler delay for testing purposes.

    Args:
        feed_name: Human-readable identifier for this feed
        feed_url: URL of the RSS feed XML
        tags_extra: Additional tags to apply to articles
        max_items: Maximum number of articles to enqueue from this feed
    """
    log(f"\n[RSS_IMMEDIATE_TEST] Parsing RSS feed: {feed_name}")
    log(f"Feed URL: {feed_url}")

    try:
        # Parse the RSS feed
        feed = feedparser.parse(feed_url)

        if feed.bozo:
            log(f"Warning: Feed parsing had issues: {feed.bozo_exception}")

        entries = feed.entries[:max_items] if max_items else feed.entries
        log(f"Found {len(feed.entries)} total entries, testing first {len(entries)}")

        # Build tags
        tags = ["policy-pulse-test", "rss", "immediate-test"]
        if tags_extra:
            tags.extend(tags_extra)

        # Enqueue each article URL
        enqueued_count = 0
        for entry in entries:
            article_url = entry.get('link')
            if not article_url:
                log(f"  Skipping entry without link: {entry.get('title', 'No title')}")
                continue

            article_title = entry.get('title', 'No title')
            log(f"  Enqueueing: {article_title}")
            log(f"    URL: {article_url}")

            # Enqueue this article URL for crawling
            enqueue_crawl(article_url, tags_extra=tags)
            enqueued_count += 1

        log(f"Successfully enqueued {enqueued_count} articles from {feed_name}")

    except Exception as e:
        log(f"Error testing RSS feed {feed_name}: {e}")


def main():
    log("=== PolicyPulse crawler API smoke test ===")

    health_check()

    # First, enqueue ALL URLs (fast, robust)
    log("\n=== Enqueueing all URLs ===")
    for url in URLS_TO_TEST:
        enqueue_crawl(url)

    # Then, optionally, try to get synchronous responses
    log("\n=== Testing url_response for each URL ===")
    for url in URLS_TO_TEST:
        call_url_response(url)

    # Test RSS feeds - TWO approaches
    log("\n=== Testing RSS feeds ===")
    if not RSS_FEEDS:
        log("No RSS feeds configured.")
    else:
        # Approach 1: Immediate testing - parse RSS and enqueue articles NOW
        log("\n--- Approach 1: IMMEDIATE testing (bypasses scheduler) ---")
        log("Parsing RSS feeds and enqueuing article URLs directly for immediate testing.")
        for site, feed_url in RSS_FEEDS.items():
            test_rss_feed_immediate(site, feed_url, tags_extra=["health-news"], max_items=3)

        # Approach 2: Configure for automated monitoring (runs every 10 minutes)
        log("\n--- Approach 2: Configure for AUTOMATED monitoring ---")
        log("NOTE: These feeds will be checked every 10 minutes by the harvester scheduler.")
        log("Articles will be automatically enqueued for crawling as they are discovered.")
        log("This is the production approach but takes 10+ minutes to see results.")
        for site, feed_url in RSS_FEEDS.items():
            configure_rss_feed(site, feed_url, tags_extra=["health-news"], max_items=5)


if __name__ == "__main__":
    main()
