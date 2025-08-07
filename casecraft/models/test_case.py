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
    status: int = Field(..., description="Expected HTTP status code")
    resp_schema: Optional[Dict[str, Any]] = Field(
        None, description="Expected response structure JSON Schema"
    )
    resp_headers: Dict[str, Any] = Field(
        default_factory=dict, description="Expected response headers"
    )
    resp_content: Optional[Dict[str, Any]] = Field(
        None, description="Expected response content assertions"
    )
    rules: List[str] = Field(
        default_factory=list, description="Business logic validation rules"
    )
    test_type: TestType = Field(..., description="Test type: positive/negative/boundary")

    def model_dump(self, **kwargs):
        """Custom model dump to exclude None and empty dict parameters."""
        data = super().model_dump(**kwargs)
        
        # Remove path_params if None or empty dict
        if 'path_params' in data:
            if data['path_params'] is None or data['path_params'] == {}:
                del data['path_params']
        
        # Remove query_params if None or empty dict
        if 'query_params' in data:
            if data['query_params'] is None or data['query_params'] == {}:
                del data['query_params']
        
        return data

    def model_dump_json(self, **kwargs):
        """Custom JSON serialization."""
        kwargs['exclude_none'] = True
        return super().model_dump_json(**kwargs)

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
    metadata: TestCaseMetadata = Field(default_factory=TestCaseMetadata)
    
    def model_dump(self, **kwargs):
        """Custom model dump to ensure test cases are properly serialized."""
        data = super().model_dump(**kwargs)
        
        # Ensure each test case in the collection is properly cleaned
        if 'test_cases' in data:
            cleaned_test_cases = []
            for test_case_data in data['test_cases']:
                # Remove path_params if None or empty dict
                if 'path_params' in test_case_data:
                    if test_case_data['path_params'] is None or test_case_data['path_params'] == {}:
                        del test_case_data['path_params']
                
                # Remove query_params if None or empty dict
                if 'query_params' in test_case_data:
                    if test_case_data['query_params'] is None or test_case_data['query_params'] == {}:
                        del test_case_data['query_params']
                
                cleaned_test_cases.append(test_case_data)
            
            data['test_cases'] = cleaned_test_cases
        
        return data
    
    def model_dump_json(self, **kwargs):
        """Custom JSON serialization to ensure proper cleaning."""
        import json
        # Extract JSON-specific kwargs
        indent = kwargs.pop('indent', None)
        exclude_none = kwargs.pop('exclude_none', True)
        # Use our custom model_dump method
        cleaned_data = self.model_dump(exclude_none=exclude_none)
        # Custom encoder for datetime objects
        from datetime import datetime
        def json_encoder(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f'Object of type {type(obj)} is not JSON serializable')
        
        return json.dumps(cleaned_data, indent=indent, ensure_ascii=False, default=json_encoder)
    
    class Config:
        """Pydantic configuration."""
        
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }