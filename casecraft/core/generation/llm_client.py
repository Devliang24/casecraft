"""LLM client implementation."""

import asyncio
import json
from typing import Any, Dict, Optional

import httpx
from pydantic import BaseModel

from casecraft.models.config import LLMConfig
from casecraft.utils.logging import get_logger


class LLMError(Exception):
    """LLM related errors."""
    pass


class LLMRateLimitError(LLMError):
    """Rate limit exceeded error."""
    pass


class LLMResponse(BaseModel):
    """LLM response container."""
    
    content: str
    model: str
    usage: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None
    retry_count: int = 0  # Number of retries performed for this request


class LLMClient:
    """Universal LLM client adapter for all providers."""
    
    def __init__(self, provider):
        """Initialize LLM client.
        
        Args:
            provider: LLMProvider instance (required)
        """
        self.logger = get_logger("llm_client")
        
        if not provider:
            raise ValueError("Provider instance is required")
            
        self.provider = provider
        self.config = getattr(provider, 'config', None)
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        progress_callback: Optional[callable] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate response using provider.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            progress_callback: Progress callback function
            **kwargs: Additional generation parameters
            
        Returns:
            LLM response
            
        Raises:
            LLMError: If generation fails
        """
        try:
            # Delegate to provider
            provider_response = await self.provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                progress_callback=progress_callback,
                **kwargs
            )
            
            # Convert provider response to LLMClient response
            return LLMResponse(
                content=provider_response.content,
                model=provider_response.model,
                usage=provider_response.token_usage.__dict__ if provider_response.token_usage else None,
                finish_reason=provider_response.metadata.get("finish_reason") if provider_response.metadata else None,
                retry_count=provider_response.metadata.get("retry_count", 0) if provider_response.metadata else 0
            )
            
        except Exception as e:
            self.logger.error(f"Provider generation failed: {str(e)}")
            raise LLMError(f"Provider error: {e}") from e
    
    async def close(self) -> None:
        """Close provider."""
        if hasattr(self.provider, 'close'):
            await self.provider.close()


