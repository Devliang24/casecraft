"""Configuration data models."""

from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, validator


class LLMConfig(BaseModel):
    """BigModel LLM configuration."""
    
    model: Optional[str] = Field(None, description="BigModel model name (must be configured via CASECRAFT_LLM_MODEL)")
    api_key: Optional[str] = Field(None, description="API key for BigModel service")
    base_url: Optional[str] = Field(default="https://open.bigmodel.cn/api/paas/v4", description="BigModel API base URL")
    timeout: int = Field(default=120, description="Request timeout in seconds")
    max_retries: int = Field(default=5, description="Maximum retry attempts")
    temperature: float = Field(default=0.7, description="Temperature for generation")
    think: bool = Field(default=False, description="Enable thinking process output (useful for debugging)")
    stream: bool = Field(default=True, description="Enable streaming response (default enabled for better user experience)")


class OutputConfig(BaseModel):
    """Output configuration."""
    
    directory: str = Field(default="test_cases", description="Output directory")
    organize_by_tag: bool = Field(default=False, description="Organize files by tag")
    filename_template: str = Field(
        default="{method}_{path_slug}.json",
        description="Template for output filenames"
    )


class ProcessingConfig(BaseModel):
    """Processing configuration."""
    
    workers: int = Field(default=1, description="Number of concurrent workers (BigModel only supports single concurrency)")
    include_tags: List[str] = Field(default_factory=list, description="Tags to include")
    exclude_tags: List[str] = Field(default_factory=list, description="Tags to exclude")
    include_paths: List[str] = Field(default_factory=list, description="Path patterns to include")
    exclude_paths: List[str] = Field(default_factory=list, description="Path patterns to exclude")
    force_regenerate: bool = Field(default=False, description="Force regenerate all test cases")
    dry_run: bool = Field(default=False, description="Preview mode without LLM calls")


class CaseCraftConfig(BaseModel):
    """Main CaseCraft configuration."""
    
    llm: LLMConfig = Field(default_factory=LLMConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    
    @validator("llm", pre=True)
    def validate_llm_config(cls, v):
        """Validate LLM configuration."""
        if isinstance(v, dict):
            return LLMConfig(**v)
        return v
    
    @validator("output", pre=True)
    def validate_output_config(cls, v):
        """Validate output configuration."""
        if isinstance(v, dict):
            return OutputConfig(**v)
        return v
    
    @validator("processing", pre=True)
    def validate_processing_config(cls, v):
        """Validate processing configuration."""
        if isinstance(v, dict):
            return ProcessingConfig(**v)
        return v

