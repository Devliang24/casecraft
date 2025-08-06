"""Test case data models."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TestType(str, Enum):
    """Test case types."""
    
    POSITIVE = "positive"
    NEGATIVE = "negative"
    BOUNDARY = "boundary"


class TestCaseMetadata(BaseModel):
    """Metadata for a test case."""
    
    generated_at: datetime = Field(default_factory=datetime.now)
    api_version: Optional[str] = None
    llm_model: Optional[str] = None


class TestCase(BaseModel):
    """A single test case definition."""
    
    test_id: int = Field(..., description="Test case ID/sequence number")
    name: str = Field(..., description="Test case name")
    description: str = Field(..., description="Test case detailed description")
    method: str = Field(..., description="HTTP method (GET/POST/PUT/DELETE/etc)")
    path: str = Field(..., description="API path (e.g. '/users/{id}')")
    headers: Dict[str, Any] = Field(default_factory=dict, description="Request headers")
    path_params: Optional[Dict[str, Any]] = Field(None, description="Path parameters")
    query_params: Optional[Dict[str, Any]] = Field(None, description="Query parameters")
    body: Optional[Dict[str, Any]] = Field(None, description="Request body data")
    expected_status: int = Field(..., description="Expected HTTP status code")
    expected_response_schema: Optional[Dict[str, Any]] = Field(
        None, description="Expected response structure JSON Schema"
    )
    expected_response_headers: Dict[str, Any] = Field(
        default_factory=dict, description="Expected response headers"
    )
    expected_response_content: Optional[Dict[str, Any]] = Field(
        None, description="Expected response content assertions"
    )
    business_rules: List[str] = Field(
        default_factory=list, description="Business logic validation rules"
    )
    test_type: TestType = Field(..., description="Test type: positive/negative/boundary")
    tags: List[str] = Field(default_factory=list, description="Test tag list")

    class Config:
        """Pydantic configuration."""
        
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class TestCaseCollection(BaseModel):
    """A collection of test cases for an API endpoint."""
    
    endpoint_id: str = Field(..., description="Unique endpoint identifier")
    method: str = Field(..., description="HTTP method")
    path: str = Field(..., description="API path")
    summary: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    test_cases: List[TestCase] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)
    metadata: TestCaseMetadata = Field(default_factory=TestCaseMetadata)
    
    class Config:
        """Pydantic configuration."""
        
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }