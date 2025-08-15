"""LLM client implementation."""

import asyncio
import json
from typing import Any, Dict, Optional

import httpx
from pydantic import BaseModel

from casecraft.models.config import LLMConfig
from casecraft.utils.logging import CaseCraftLogger


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
        self.logger = CaseCraftLogger("llm_client", show_timestamp=True, show_level=True)
        
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
            # Log request details
            provider_name = self.provider.name if hasattr(self.provider, 'name') else 'unknown'
            model = self.provider.config.model if hasattr(self.provider, 'config') else 'unknown'
            
            self.logger.file_only(f"📤 Sending request to {provider_name} provider (model: {model})")
            
            # Log request parameters
            request_params = {
                "temperature": kwargs.get("temperature", self.provider.config.temperature if hasattr(self.provider, 'config') else 0.7),
                "max_tokens": kwargs.get("max_tokens", getattr(self.provider.config, 'max_tokens', 8192) if hasattr(self.provider, 'config') else 8192),
                "stream": getattr(self.provider.config, 'stream', False) if hasattr(self.provider, 'config') else False
            }
            self.logger.file_only(f"Request params: temperature={request_params['temperature']}, "
                            f"max_tokens={request_params['max_tokens']}, stream={request_params['stream']}", level="DEBUG")
            
            # Track timing
            import time
            start_time = time.time()
            
            # Log waiting state
            if request_params['stream']:
                self.logger.file_only("⏳ Waiting for streaming response...")
            else:
                self.logger.file_only("⏳ Waiting for LLM response...")
            
            # Delegate to provider
            provider_response = await self.provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                progress_callback=progress_callback,
                **kwargs
            )
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Log response received
            response_tokens = provider_response.token_usage.completion_tokens if provider_response.token_usage else 0
            self.logger.file_only(f"✅ Response received in {duration:.1f}s ({response_tokens:,} tokens)")
            
            # Convert provider response to LLMClient response
            self.logger.file_only(f"Provider response token_usage: {provider_response.token_usage}", level="DEBUG")
            
            usage_dict = None
            if provider_response.token_usage:
                usage_dict = {
                    "prompt_tokens": provider_response.token_usage.prompt_tokens,
                    "completion_tokens": provider_response.token_usage.completion_tokens,
                    "total_tokens": provider_response.token_usage.total_tokens
                }
                self.logger.file_only(f"Converted token usage to dict: {usage_dict}", level="DEBUG")
            
            return LLMResponse(
                content=provider_response.content,
                model=provider_response.model,
                usage=usage_dict,
                finish_reason=provider_response.metadata.get("finish_reason") if provider_response.metadata else None,
                retry_count=provider_response.metadata.get("retry_count", 0) if provider_response.metadata else 0
            )
            
        except Exception as e:
            self.logger.file_only(f"Provider generation failed: {str(e)}", level="ERROR")
            raise LLMError(f"Provider error: {e}") from e
    
    async def close(self) -> None:
        """Close provider."""
        if hasattr(self.provider, 'close'):
            await self.provider.close()


