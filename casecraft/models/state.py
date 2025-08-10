"""State management data models."""

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


class EndpointState(BaseModel):
    """State information for a single endpoint."""
    
    definition_hash: str = Field(..., description="Hash of endpoint definition")
    last_generated: datetime = Field(..., description="Last generation timestamp")
    test_cases_count: int = Field(default=0, description="Number of generated test cases")
    output_file: Optional[str] = Field(None, description="Path to generated JSON file")
    provider_used: Optional[str] = Field(None, description="Provider used for generation")
    tokens_used: Optional[int] = Field(None, description="Tokens used for generation")


class ProcessingStatistics(BaseModel):
    """Statistics for processing run."""
    
    total_endpoints: int = Field(default=0)
    generated_count: int = Field(default=0) 
    skipped_count: int = Field(default=0)
    failed_count: int = Field(default=0)
    last_run_duration: Optional[float] = Field(None, description="Duration in seconds")
    provider_usage: Dict[str, int] = Field(default_factory=dict, description="Usage count per provider")
    provider_success_rate: Dict[str, float] = Field(default_factory=dict, description="Success rate per provider")
    provider_avg_tokens: Dict[str, float] = Field(default_factory=dict, description="Average tokens per provider")


class ProjectConfig(BaseModel):
    """Configuration stored in state file."""
    
    api_source: str = Field(..., description="URL or file path of API source")
    last_modified: datetime = Field(..., description="Last modification timestamp")
    source_hash: str = Field(..., description="MD5 hash of API document content")


class CaseCraftState(BaseModel):
    """Main state tracking for CaseCraft project."""
    
    version: str = Field(default="1.0", description="State file format version")
    config: Optional[ProjectConfig] = None
    endpoints: Dict[str, EndpointState] = Field(default_factory=dict)
    statistics: ProcessingStatistics = Field(default_factory=ProcessingStatistics)
    
    class Config:
        """Pydantic configuration."""
        
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    def get_endpoint_state(self, endpoint_id: str) -> Optional[EndpointState]:
        """Get state for a specific endpoint."""
        return self.endpoints.get(endpoint_id)
    
    def update_endpoint_state(self, endpoint_id: str, state: EndpointState) -> None:
        """Update state for a specific endpoint."""
        self.endpoints[endpoint_id] = state
    
    def is_endpoint_unchanged(self, endpoint_id: str, definition_hash: str) -> bool:
        """Check if endpoint definition is unchanged."""
        state = self.get_endpoint_state(endpoint_id)
        return state is not None and state.definition_hash == definition_hash