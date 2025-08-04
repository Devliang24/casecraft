"""CaseCraft: A CLI tool for API testing that parses API documentation and uses LLM to generate structured test case data."""

__version__ = "0.1.0"
__author__ = "CaseCraft Team"
__email__ = "team@casecraft.dev"

from casecraft.models.config import CaseCraftConfig
from casecraft.models.test_case import TestCase, TestType

__all__ = [
    "__version__",
    "__author__", 
    "__email__",
    "CaseCraftConfig",
    "TestCase",
    "TestType",
]