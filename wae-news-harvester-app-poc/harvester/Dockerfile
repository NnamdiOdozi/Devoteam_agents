FROM python:3.13-slim

# Build-time configurable argument for data directory
ARG BROWSER_PROFILE_SOURCE=harvester/browser-profile
ENV BROWSER_PROFILE=/tmp/browser_profile

# Set working directory
WORKDIR /app

# Install system dependencies and uv
RUN apt-get update && apt-get install -y \
    curl \
    cargo \
    g++ \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip \
    && pip install uv

# Copy pyproject.toml first for better caching
COPY pyproject.toml .

# Install Python dependencies using uv
RUN uv pip install --system --no-cache -r pyproject.toml \
    && crawl4ai-setup

# Create configurable data directory
RUN mkdir -p ${BROWSER_PROFILE}
# Copy application code
COPY harvester/ ./harvester

COPY core/ ./core

# Set environment variable for runtime access to data directory
COPY ${BROWSER_PROFILE_SOURCE} ${BROWSER_PROFILE}

# Create non-root user
# RUN useradd -m -u 1001 appuser && chown -R appuser:appuser /app
# USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "-m", "harvester.app.main"]


