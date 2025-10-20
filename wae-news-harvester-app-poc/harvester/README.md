# Harvester Configuration Management

This directory contains tools and configurations for the news harvester system.

## Web Crawling with Crawl4AI

The harvester uses [Crawl4AI](https://github.com/unclecode/crawl4ai) for web scraping, which provides advanced crawling capabilities with browser automation.

### Identity-Based Crawling

The crawler implements **identity-based crawling** using a persistent Chromium browser profile. This approach allows the crawler to:

- Maintain cookies and session data across crawls
- Preserve authentication states
- Bypass certain anti-bot measures
- Maintain consistent browser fingerprints

### Browser Profile Configuration

The browser profile is configured via the `harvester_browser_profile` setting in the Harvester configuration. By default, it uses a statically defined Chromium profile located at:

```
./harvester/browser-profile
```

This profile directory contains all browser state including:
- Cookies and session storage
- Local storage data
- Browser preferences
- Cache and history

### Updating the Browser Profile

To update or modify the browser profile (e.g., to log into websites, accept cookies, or configure browser settings), you need to run Chromium directly with the profile directory:

```bash
# Run Chromium with the harvester browser profile
chromium --user-data-dir=./harvester/browser-profile
```

Or on macOS:

```bash
# Run Chromium with the harvester browser profile on macOS
/Applications/Chromium.app/Contents/MacOS/Chromium --user-data-dir=./harvester/browser-profile
```

**Important Notes:**
- Make sure the harvester is not running when you modify the browser profile
- Any changes made in the browser (logins, cookie acceptances, etc.) will be persisted to the profile directory
- The profile directory should be committed to version control if you want to share authentication states across deployments
- Be careful not to commit sensitive credentials or personal data in the browser profile

### How It Works

When the crawler runs:
1. Crawl4AI launches a Chromium instance using the specified profile directory
2. The browser loads with all saved cookies, sessions, and preferences
3. Web pages are crawled with the authenticated/configured browser state
4. Any new cookies or session data are automatically saved back to the profile

This identity-based approach is particularly useful for:
- Crawling sites that require cookie consent
- Accessing content behind authentication
- Maintaining consistent crawling behavior
- Reducing the likelihood of being blocked by anti-bot systems

## Configuration Import Tool

The `import-config.py` script allows importing harvester configuration JSON files into DynamoDB. This tool validates the configuration using the Pydantic models and converts it to DynamoDB format.

### Prerequisites

- Python 3.8+
- AWS CLI configured with appropriate permissions
- Virtual environment activated (`.venv`)

### Usage

```bash
python import-config.py <json_file_path> [--task-id <task_id>] [--format <format>]
```

#### Options

- `<json_file_path>`: Path to the JSON configuration file (required)
- `--task-id <task_id>`: Optional task ID to filter for a specific task
- `--format <format>`: Output format (default: 'single')
  - `single`: Output a single task for use with `put-item`
  - `batch`: Output all tasks in BatchWriteItem format
  - `all`: Output all tasks as a JSON array

### Examples

#### 1. Import a Single Task

To import a specific task from the configuration file:

```bash
# Activate the virtual environment
source .venv/bin/activate

# Import a specific task
aws dynamodb put-item \
  --table-name <config-table-name> \
  --item "$(python harvester/import-config.py harvester/harvester_scrape_config.json --task-id bbc-news-health-rss | cat)"
```

#### 2. Import All Tasks Using BatchWriteItem

To import all tasks at once using the BatchWriteItem operation:

```bash
# Activate the virtual environment
source .venv/bin/activate

# Import all tasks
aws dynamodb batch-write-item \
  --request-items "$(python harvester/import-config.py harvester/harvester_scrape_config.json --format batch | cat)"
```

#### 3. Import All Tasks One by One

To import all tasks one by one using a shell script:

```bash
# Activate the virtual environment
source .venv/bin/activate

# Get all tasks in JSON array format
tasks=$(python harvester/import-config.py harvester/harvester_scrape_config.json --format all)

# Loop through each task and import it
echo "$tasks" | jq -c '.[]' | while read -r task; do
  aws dynamodb put-item \
    --table-name <config-table-name> \
    --item "$task"
done
```

### Configuration File Format

The configuration file should follow the structure defined in the `HarvesterConfig` model in `core/models.py`. See `harvester_scrape_config.json` and `example-harvester-scrape-config.json.example` for examples.

### Troubleshooting

- If you encounter errors about missing modules, make sure you have activated the virtual environment.
- If you get validation errors, check that your JSON configuration follows the required schema.
- For AWS CLI errors, verify that your AWS credentials are properly configured and have the necessary permissions.