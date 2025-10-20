# News Harvester Agent

This application crawls news articles from various sources, extracts content using AWS Bedrock, and stores the results in DynamoDB and S3.

## Project Structure

```
.
├── README.md                          # This file
├── Makefile                           # Build and deployment tasks
├── docker-compose.yml                 # Docker services configuration
├── pyproject.toml                     # Python project dependencies
├── .env-sample                        # Sample environment configuration
├── .python-version                    # Python version specification
│
├── core/                              # Shared core utilities
│   ├── __init__.py
│   ├── config.py                      # Configuration management
│   ├── logging_config.py              # Logging setup
│   ├── models.py                      # Data models
│   ├── s3_utils.py                    # S3 operations
│   ├── sqs_consumer.py                # SQS message consumer
│   └── sqs_utils.py                   # SQS utilities
│
├── harvester/                         # News harvester service
│   ├── Dockerfile                     # Container image for harvester
│   ├── Dockerfile.lambda              # Lambda deployment image
│   ├── README.md                      # Harvester-specific documentation
│   ├── harvester_scrape_config.json   # Scraping configuration
│   ├── import-config.py               # Config import utility
│   │
│   ├── app/                           # Application code
│   │   ├── __init__.py
│   │   ├── main.py                    # Application entry point
│   │   ├── bedrock_token.py           # AWS Bedrock token handling
│   │   ├── crawler.py                 # Web crawling logic
│   │   ├── dynamodb.py                # DynamoDB operations
│   │   ├── message_processor.py       # SQS message processing
│   │   ├── rss_processor.py           # RSS feed processing
│   │   └── api/                       # API endpoints
│   │
│   └── browser-profile/               # Chromium browser profile data
│
├── crawled/                           # Local storage for crawled articles
│   └── [source-name]/                 # Organized by source
│       └── YYYY/MM/DD/[hash]/         # Date-based structure
│           ├── article.json           # Article metadata
│           ├── article.pdf            # PDF version
│           └── article.txt            # Text content
│
└── diagrams/                          # Architecture diagrams
```

## Prerequisites

- Python 3.x (version specified in [`.python-version`](.python-version))
- Docker and Docker Compose (for containerized deployment)
- AWS Account with appropriate permissions
- Make utility (for running Makefile tasks)

## Quick Start

### 1. Environment Configuration

The application requires proper environment configuration before running. A sample configuration file is provided:

1. **Duplicate the sample environment file:**
   ```bash
   cp .env-sample .env
   ```

2. **Edit the `.env` file** and provide the correct values for your environment:

   ```bash
   # AWS Credentials (required for Bedrock token generation)
   AWS_ACCESS_KEY_ID=your-aws-access-key
   AWS_SECRET_ACCESS_KEY=your-aws-secret-key
   AWS_REGION=eu-central-1
   BEDROCK_AWS_REGION=eu-central-1

   # DynamoDB Tables
   DYNAMODB_STATE_TABLE_NAME=wae-news-agents-documents-table
   DYNAMODB_RSS_PROCESSED_TABLE_NAME=wae-news-agents-documents-table-rss-processed
   HARVESTER_CONFIG_TABLE=wae-harvester-config-table

   # SQS Queues
   HARVESTER_SQS_QUEUE_NAME=harvester-ingest-queue
   VERIFIER_SQS_QUEUE_NAME=verifier-ingest-queue

   # S3 Storage
   S3_BUCKET_NAME=wae-news-agent-documents-2a4f

   # Browser Profile Path
   HARVESTER_BROWSER_PROFILE=./harvester/browser-profile
   ```

3. **Required AWS Resources:**
   - **DynamoDB Tables:** Ensure the following tables exist in your AWS account:
     - `wae-news-agents-documents-table` - Main document storage
     - `wae-news-agents-documents-table-rss-processed` - RSS feed processing state
     - `wae-harvester-config-table` - Harvester configuration

   - **SQS Queues:** Create the following queues:
     - `harvester-ingest-queue` - Queue for harvester tasks
     - `verifier-ingest-queue` - Queue for verification tasks

   - **S3 Bucket:** Create an S3 bucket (e.g., `wae-news-agent-documents-2a4f`)

4. **AWS Permissions:** Your AWS credentials must have access to:
   - Amazon Bedrock (for content extraction)
   - DynamoDB (read/write access to tables)
   - S3 (read/write access to bucket)
   - SQS (send/receive messages)

### 2. Local Development Setup

The project uses a [`Makefile`](Makefile) to simplify common tasks. Available commands:

#### Install Dependencies
```bash
make install
```
Creates a virtual environment and installs all required Python dependencies using `uv`.

#### Start the Harvester (Local)
```bash
make start-harvester
```
Starts the News Harvester API locally (requires virtual environment to be activated).

#### Clean Environment
```bash
make clean
```
Removes the virtual environment (`.venv` directory).

### 3. Docker Compose Deployment

The application includes a [`docker-compose.yml`](docker-compose.yml) file for containerized deployment with LocalStack for local AWS service emulation.

#### Services Included

1. **Harvester Service**
   - Builds from [`./harvester/Dockerfile`](harvester/Dockerfile)
   - Exposes port `8000` for the API
   - Includes hot-reload support for development
   - Health check endpoint: `http://localhost:8000/api/v1/health`

2. **LocalStack Service**
   - Provides local AWS service emulation (DynamoDB, SQS, S3)
   - Exposes port `4566` for all AWS services
   - Useful for local development and testing without AWS costs

#### Docker Commands

**Build containers:**
```bash
make build
```
Builds Docker images from scratch (no cache).

**Start all services:**
```bash
make start
```
Starts both the harvester and LocalStack services in detached mode.

**Stop all services:**
```bash
make stop
```
Stops and removes all running containers.

**Manual Docker Compose commands:**
```bash
# Start services in foreground (see logs)
docker-compose up

# Start services in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Rebuild and start
docker-compose up --build
```

#### Using LocalStack for Local Development

When using LocalStack, the application will connect to local AWS services instead of real AWS:

- **DynamoDB:** `http://localstack:4566`
- **SQS:** `http://localstack:4566`
- **S3:** `http://localstack:4566`

LocalStack initialization scripts can be placed in [`./localstack-init`](./localstack-init) directory to automatically create resources on startup.

### 4. AWS Bedrock Setup

1. Ensure you have access to AWS Bedrock in your AWS account
2. Request access to the models you want to use (e.g., Claude models)
3. Set the `BEDROCK_AWS_REGION` to the region where Bedrock is available

