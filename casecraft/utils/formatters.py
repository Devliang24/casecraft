"""Output formatters for test cases."""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

from casecraft.models.test_case import TestCaseCollection


class OutputFormatter(ABC):
    """Abstract base class for output formatters."""
    
    @abstractmethod
    def format(self, collection: TestCaseCollection) -> str:
        """Format test case collection to string.
        
        Args:
            collection: Test case collection to format
            
        Returns:
            Formatted string
        """
        pass
    
    @abstractmethod
    def get_file_extension(self) -> str:
        """Get file extension for this format.
        
        Returns:
            File extension (including dot)
        """
        pass


class JSONFormatter(OutputFormatter):
    """JSON output formatter."""
    
    def __init__(self, indent: int = 2):
        """Initialize JSON formatter.
        
        Args:
            indent: JSON indentation level
        """
        self.indent = indent
    
    def format(self, collection: TestCaseCollection) -> str:
        """Format collection as JSON."""
        return collection.model_dump_json(indent=self.indent, exclude_none=True)
    
    def get_file_extension(self) -> str:
        """Get JSON file extension."""
        return ".json"


class CompactJSONFormatter(OutputFormatter):
    """Compact JSON output formatter (no indentation)."""
    
    def format(self, collection: TestCaseCollection) -> str:
        """Format collection as compact JSON."""
        return collection.model_dump_json(exclude_none=True)
    
    def get_file_extension(self) -> str:
        """Get JSON file extension."""
        return ".json"


class PrettyJSONFormatter(OutputFormatter):
    """Pretty-printed JSON formatter with extra formatting."""
    
    def format(self, collection: TestCaseCollection) -> str:
        """Format collection as pretty JSON with metadata."""
        data = collection.model_dump(exclude_none=True)
        
        # Add formatting metadata
        formatted_data = {
            "_metadata": {
                "format": "CaseCraft Test Cases",
                "version": "1.0",
                "endpoint": f"{collection.method} {collection.path}",
                "total_test_cases": len(collection.test_cases)
            },
            **data
        }
        
        return json.dumps(formatted_data, indent=2, ensure_ascii=False, sort_keys=False)
    
    def get_file_extension(self) -> str:
        """Get JSON file extension."""
        return ".json"


def get_formatter(format_type: str = "json") -> OutputFormatter:
    """Get formatter instance by type.
    
    Args:
        format_type: Format type (json, compact, pretty)
        
    Returns:
        Formatter instance
        
    Raises:
        ValueError: If format type is unsupported
    """
    formatters = {
        "json": JSONFormatter,
        "compact": CompactJSONFormatter,
        "pretty": PrettyJSONFormatter
    }
    
    if format_type not in formatters:
        supported = ", ".join(formatters.keys())
        raise ValueError(f"Unsupported format type: {format_type}. Supported: {supported}")
    
    return formatters[format_type]()