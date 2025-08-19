"""Configuration models for multiple LLM providers."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    """Configuration for a single provider."""
    
    name: str = Field(..., description="Provider name")
    model: str = Field(..., description="Model name")
    api_key: Optional[str] = Field(None, description="API key for authentication")
    base_url: Optional[str] = Field(None, description="Base URL for API")
    timeout: int = Field(120, description="Request timeout in seconds")
    max_retries: int = Field(3, description="Maximum number of retries")
    temperature: float = Field(0.7, description="Temperature for generation")
    stream: bool = Field(True, description="Whether to stream responses")
    workers: int = Field(1, description="Maximum concurrent workers")
    use_structured_output: bool = Field(True, description="Use structured output format for JSON responses")
    max_tokens: int = Field(8192, description="Maximum tokens for completion")
    
    class Config:
        extra = "allow"  # Allow additional provider-specific fields


class MultiProviderConfig(BaseModel):
    """Configuration for multiple providers."""
    
    providers: List[str] = Field(
        default_factory=list,
        description="List of enabled providers"
    )
    configs: Dict[str, ProviderConfig] = Field(
        default_factory=dict,
        description="Provider configurations"
    )
    strategy: str = Field(
        "round_robin",
        description="Provider assignment strategy"
    )
    selected_provider: Optional[str] = Field(
        None,
        description="User-specified provider for single-provider mode"
    )
    fallback_enabled: bool = Field(
        True,
        description="Whether to enable fallback to other providers"
    )
    fallback_chain: List[str] = Field(
        default_factory=list,
        description="Fallback chain of providers"
    )
    
    def validate_provider_specified(self) -> bool:
        """Check if at least one provider is specified.
        
        Returns:
            True if provider is specified
        """
        return bool(self.selected_provider or self.providers)
    
    def get_active_providers(self) -> List[str]:
        """Get list of active providers.
        
        Returns:
            List of provider names
        """
        if self.selected_provider:
            return [self.selected_provider]
        return self.providers or []