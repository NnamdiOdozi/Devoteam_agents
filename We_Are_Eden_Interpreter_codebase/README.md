# Policy Assessment Tool

Compares company policies against UK employment legislation, guidelines, and current news using AWS Bedrock (Claude Sonnet 4) via Strands agents. Generates actionable recommendations for compliance and best practices.

## Prerequisites

- Python 3.12
- AWS account with Bedrock access (us-east-1 region)
- Docker (optional)

## Quick Setup

### Local Development

```bash
# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure AWS credentials
cp .env.example .env
# Edit .env with your AWS credentials:
# AWS_REGION=us-east-1
# AWS_ACCESS_KEY_ID=your_key
# AWS_SECRET_ACCESS_KEY=your_secret
```

### Run Web Server

```bash
python -m uvicorn backend.server:app --host 0.0.0.0 --port 8000
```

Access at `http://localhost:8000`

### Run CLI

```bash
# Assess default policy (NHS maternity)
python -m backend.cli

# Assess specific policy
python -m backend.cli \
  --policy "data/Customer/Manchester Univ - Time off for Fertility Treatment Policy.pdf" \
  --category fertility

# Save results to file
python -m backend.cli --output results.json
```

### Docker

```bash
# Build and run
docker-compose up --build

# Or manually
docker build -t policy-assessment .
docker run -p 8000:8000 --env-file .env policy-assessment
```

## Architecture

### Backend (`backend/`)

**server.py**
- FastAPI application with SSE streaming
- Endpoints: `/api/assess`, `/api/categories`, `/health`
- Serves frontend static files

**assessor.py**
- Core assessment engine
- Creates fresh Strands Agent per comparison
- Uses Claude Sonnet 4 with 1M token context window
- Processes reference documents in parallel

**models.py**
- Pydantic models for structured output
- Enforces exactly 3 recommendations per document
- Priority levels: HIGH/MEDIUM/LOW

**loader.py**
- Handles PDF/TXT/DOCX files
- Validates PDF page count (max 100 pages)
- Returns bytes + media type for Bedrock

**cli.py**
- Click-based CLI interface
- Outputs formatted results or JSON

### Frontend (`frontend/`)

Vanilla JavaScript SPA with modular architecture:

- `ApiClient.js` - SSE client for real-time updates
- `FileHandler.js` - File validation and upload
- `UIManager.js` - UI state management
- `ResultsRenderer.js` - Dynamic results display
- `ModalManager.js` - Document detail modals

### Configuration

**config/document_categories.json**

Maps 4 policy categories to reference documents:
- `maternity` - 13 reference documents
- `fertility` - 11 reference documents  
- `menopause` - 13 reference documents
- `breastfeeding` - 11 reference documents

Each category includes:
- Legislation (UK employment law PDFs)
- Guidelines (best practice documents)
- News (current articles as TXT files)

### Data Structure

```
data/
├── Customer/           # Policies to assess
├── Legislations/       # UK employment law (PDF)
├── Guidlines/          # Best practices (PDF/DOCX)
└── News/              # Current articles (TXT)
    ├── maternity-leave/
    ├── fertility/
    ├── menopause/
    └── breastfeeding/
```

## How It Works

1. User uploads company policy PDF via web UI or CLI
2. System loads policy and all reference documents for selected category
3. For each reference document:
   - Creates fresh Strands Agent with Bedrock model
   - Passes policy + reference document to Claude
   - Agent generates exactly 3 prioritized recommendations
4. Aggregates all recommendations by document type
5. Returns structured results via SSE stream (web) or JSON (CLI)

## AWS Bedrock Configuration

Uses:
- Model: `us.anthropic.claude-sonnet-4-20250514-v1:0`
- Region: `us-east-1`
- Context window: 1M tokens (via `anthropic_beta` flag)

Credentials loaded from:
1. Environment variables (`.env` file)
2. AWS credential chain (profiles, IAM roles)

## Dependencies

Core packages:
- `fastapi` - Web framework
- `strands-agents` - Bedrock agent SDK
- `boto3` - AWS SDK
- `pydantic` - Data validation
- `PyPDF2` - PDF parsing
- `click` - CLI framework
