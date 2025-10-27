#!/usr/bin/env python3
"""
Import harvester configuration JSON file into DynamoDB.

Usage:
    python import-config.py <json_file_path> [--task-id <task_id>] [--format <format>]

Options:
    --task-id <task_id>    Optional task ID to filter for a specific task
    --format <format>      Output format: 'single' (default) for single item,
                          'batch' for BatchWriteItem format, 'all' for all items

Examples:
    # Output a single task for put-item
    python import-config.py harvester_scrape_config.json --task-id sky-news-rss

    # Output all tasks in batch format
    python import-config.py harvester_scrape_config.json --format batch

    # Output all tasks as separate items
    python import-config.py harvester_scrape_config.json --format all
"""

import json
import sys
import os
import argparse
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel

# Add parent directory to path to import core modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import HarvesterConfig, HarvesterConfigTask
from core.config import harvester_settings

def load_config(file_path: str) -> HarvesterConfig:
    """
    Load and validate the harvester configuration from a JSON file.

    Args:
        file_path: Path to the JSON configuration file

    Returns:
        HarvesterConfig: Validated configuration object
    """
    try:
        with open(file_path, 'r') as f:
            config_data = json.load(f)

        # Validate using Pydantic model
        config = HarvesterConfig.model_validate(config_data)
        return config
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        sys.exit(1)

# Simple TypeSerializer implementation to avoid boto3 dependency
class SimpleTypeSerializer:
    """
    A simplified version of boto3's TypeSerializer that converts Python types to DynamoDB format.
    """

    def serialize(self, value: Any) -> Dict[str, Any]:
        """
        Convert a Python value to a DynamoDB attribute value.
        """
        if value is None:
            return {"NULL": True}
        elif isinstance(value, bool):
            return {"BOOL": value}
        elif isinstance(value, (int, float)):
            return {"N": str(value)}
        elif isinstance(value, str):
            return {"S": value}
        elif isinstance(value, list):
            if not value:
                return {"L": []}
            if all(isinstance(item, str) for item in value):
                return {"SS": value}
            return {"L": [self.serialize(item) for item in value]}
        elif isinstance(value, dict):
            if not value:
                return {"M": {}}
            return {"M": {k: self.serialize(v) for k, v in value.items()}}
        else:
            # Convert to string as fallback
            return {"S": str(value)}

def convert_to_dynamodb_items(config: HarvesterConfig) -> List[Dict[str, Any]]:
    """
    Convert the harvester configuration to DynamoDB items.

    Args:
        config: Validated HarvesterConfig object

    Returns:
        List of DynamoDB items
    """
    items = []

    # Convert each task to a DynamoDB item
    for task in config.tasks:
        # Create a dictionary representation of the task
        task_dict = {
            "task_id": task.id,
            "task_type": task.type,
            "tags": task.tags,
            "config_data": task.model_dump(mode="json"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "version": config.version
        }

        # Convert to DynamoDB format
        serializer = SimpleTypeSerializer()
        item = {k: serializer.serialize(v) for k, v in task_dict.items()}
        items.append(item)

    return items

def format_for_cli(items: List[Dict[str, Any]], format_type: str = 'single', task_id: Optional[str] = None) -> str:
    """
    Format the DynamoDB items for use with the AWS CLI.

    Args:
        items: List of DynamoDB items
        format_type: Output format ('single', 'batch', or 'all')
        task_id: Optional task ID to filter for

    Returns:
        JSON string formatted for AWS CLI
    """
    if task_id:
        # Filter for the specific task ID
        filtered_items = [item for item in items if item.get('task_id', {}).get('S') == task_id]
        if not filtered_items:
            print(f"Error: Task ID '{task_id}' not found in configuration", file=sys.stderr)
            sys.exit(1)
        items = filtered_items

    if format_type == 'single':
        if len(items) > 1 and not task_id:
            print(f"Warning: Found {len(items)} items. Only the first item will be output.", file=sys.stderr)
        return json.dumps(items[0])

    elif format_type == 'batch':
        # Format for BatchWriteItem
        # Get the table name from settings or use a default
        table_name = harvester_settings.harvester_config_table or "harvester-config-tasks"
        batch_items = {
            table_name: [
                {"PutRequest": {"Item": item}} for item in items
            ]
        }
        return json.dumps(batch_items)

    elif format_type == 'all':
        # Return all items as a JSON array
        return json.dumps(items)

    else:
        print(f"Error: Unknown format type '{format_type}'", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Import harvester configuration JSON file into DynamoDB')
    parser.add_argument('json_file', help='Path to the JSON configuration file')
    parser.add_argument('--task-id', help='Optional task ID to filter for a specific task')
    parser.add_argument('--format', choices=['single', 'batch', 'all'], default='single',
                        help='Output format: single item, batch format, or all items')

    args = parser.parse_args()

    # Load and validate the configuration
    config = load_config(args.json_file)

    # Convert to DynamoDB items
    items = convert_to_dynamodb_items(config)

    # Format for CLI and print to stdout
    print(format_for_cli(items, args.format, args.task_id))

if __name__ == "__main__":
    main()