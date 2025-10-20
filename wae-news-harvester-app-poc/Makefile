PYTHON_VERSION := $(shell cat .python-version)
BUCKET ?= "devoteam-ai"
DEBUG ?= true
source_venv := source .venv/bin/activate

clean:
	@rm -rf .venv

install:
	@python3 -m venv .venv && $(source_venv) \
	&& pip install --upgrade pip && pip install uv \
        && uv venv -c -qq --python $(PYTHON_VERSION) && source .venv/bin/activate \
	&& uv pip install -r pyproject.toml

start-harvester:
	@echo "Starting News Harvester API..."
	eval $(source_venv) && \
	python3 -m harvester.app.main

start:
	@echo "Starting containers..."
	@docker-compose up -d

stop:
	@echo "Stopping containers..."
	@docker-compose down

build:
	@docker-compose build --no-cache
