"""API specification data models."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class APIParameter(BaseModel):
    """API parameter definition."""
    
    name: str
    location: str  # "path", "query", "header", "body"
    type: str
    required: bool = False
    description: Optional[str] = None
    param_schema: Optional[Dict[str, Any]] = Field(None, alias="schema")


class APIEndpoint(BaseModel):
    """API endpoint definition."""
    
    method: str
    path: str
    operation_id: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    parameters: List[APIParameter] = Field(default_factory=list)
    request_body: Optional[Dict[str, Any]] = None
    responses: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    
    def get_endpoint_id(self) -> str:
        """Generate unique endpoint identifier."""
        return f"{self.method.upper()}:{self.path}"


class APISpecification(BaseModel):
    """Complete API specification."""
    
    title: str
    version: str
    description: Optional[str] = None
    base_url: Optional[str] = None
    endpoints: List[APIEndpoint] = Field(default_factory=list)
    
    def get_endpoints_by_tag(self, tag: str) -> List[APIEndpoint]:
        """Get endpoints filtered by tag."""
        return [ep for ep in self.endpoints if tag in ep.tags]
    
    def get_endpoints_by_path_pattern(self, pattern: str) -> List[APIEndpoint]:
        """Get endpoints matching path pattern."""
        import fnmatch
        return [ep for ep in self.endpoints if fnmatch.fnmatch(ep.path, pattern)]
    
    def filter_endpoints(
        self,
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
        include_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None
    ) -> 'APISpecification':
        """Filter endpoints based on tags and path patterns.
        
        Args:
            include_tags: Tags to include
            exclude_tags: Tags to exclude
            include_paths: Path patterns to include
            exclude_paths: Path patterns to exclude
            
        Returns:
            New APISpecification with filtered endpoints
        """
        import fnmatch
        filtered_endpoints = []
        
        for endpoint in self.endpoints:
            # Check tag filters
            if include_tags:
                if not any(tag in endpoint.tags for tag in include_tags):
                    continue
            
            if exclude_tags:
                if any(tag in endpoint.tags for tag in exclude_tags):
                    continue
            
            # Check path filters
            if include_paths:
                if not any(fnmatch.fnmatch(endpoint.path, pattern) for pattern in include_paths):
                    continue
            
            if exclude_paths:
                if any(fnmatch.fnmatch(endpoint.path, pattern) for pattern in exclude_paths):
                    continue
            
            filtered_endpoints.append(endpoint)
        
        # Return new APISpecification with filtered endpoints
        return APISpecification(
            title=self.title,
            version=self.version,
            description=self.description,
            base_url=self.base_url,
            endpoints=filtered_endpoints
        )