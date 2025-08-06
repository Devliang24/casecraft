"""LLM client implementation."""

import asyncio
import json
from typing import Any, Dict, Optional

import httpx
from pydantic import BaseModel

from casecraft.models.config import LLMConfig


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


class LLMClient:
    """LLM API client implementation (currently using BigModel GLM-4.5-X)."""
    
    def __init__(self, config: LLMConfig):
        """Initialize BigModel client.
        
        Args:
            config: LLM configuration
        """
        self.config = config
        self.base_url = config.base_url or "https://open.bigmodel.cn/api/paas/v4"
        self._request_lock = asyncio.Lock()  # Ensure single concurrency
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=config.timeout,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json"
            }
        )
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate response using BigModel API with single concurrency.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            **kwargs: Additional generation parameters
            
        Returns:
            LLM response
            
        Raises:
            LLMError: If generation fails
            LLMRateLimitError: If rate limit is exceeded
        """
        async with self._request_lock:  # Serialize all requests
            messages = []
            
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self.config.model or "glm-4.5-x",
                "messages": messages,
                "think": self.config.think,
                "stream": self.config.stream,
                "temperature": kwargs.get("temperature", self.config.temperature)
            }
            
            try:
                response = await self._make_request_with_retry("/chat/completions", payload)
                
                choice = response["choices"][0]
                return LLMResponse(
                    content=choice["message"]["content"],
                    model=self.config.model or "glm-4.5-x",
                    usage=response.get("usage"),
                    finish_reason=choice.get("finish_reason")
                )
                
            except Exception as e:
                raise LLMError(f"BigModel API error: {e}") from e
    
    async def _make_request_with_retry(
        self, 
        endpoint: str, 
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Make HTTP request with smart retry logic.
        
        Args:
            endpoint: API endpoint
            payload: Request payload
            
        Returns:
            Response data
            
        Raises:
            LLMError: If request fails
            LLMRateLimitError: If rate limit exceeded
        """
        last_error = None
        base_wait = 2.0  # Base wait time in seconds
        
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await self.client.post(endpoint, json=payload)
                
                if response.status_code == 429:
                    # Rate limit hit - use exponential backoff with jitter
                    if attempt < self.config.max_retries:
                        # Try to get retry-after header
                        retry_after = response.headers.get('retry-after')
                        if retry_after:
                            wait_time = float(retry_after) + (0.5 * attempt)
                        else:
                            # Exponential backoff with jitter
                            wait_time = base_wait * (2 ** attempt) + (0.1 * attempt)
                            wait_time = min(wait_time, 60)  # Cap at 60 seconds
                        
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise LLMRateLimitError(
                            f"Rate limit exceeded after {self.config.max_retries} retries. "
                            f"BigModel only supports single concurrency."
                        )
                
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 429:
                    # Already handled above
                    continue
                elif e.response.status_code >= 500:
                    # Server error - retry with backoff
                    if attempt < self.config.max_retries:
                        wait_time = base_wait * (attempt + 1)
                        await asyncio.sleep(wait_time)
                        continue
                else:
                    # Client error - don't retry
                    raise LLMError(f"HTTP error {e.response.status_code}: {e}")
                    
            except httpx.RequestError as e:
                last_error = e
                if attempt < self.config.max_retries:
                    # Network error - retry with backoff
                    wait_time = base_wait * (attempt + 1)
                    await asyncio.sleep(wait_time)
                    continue
        
        # All retries exhausted
        raise LLMError(f"Request failed after {self.config.max_retries + 1} attempts: {last_error}")
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()


def create_llm_client(config: LLMConfig) -> LLMClient:
    """Create LLM client.
    
    Args:
        config: LLM configuration
        
    Returns:
        LLM client instance
    """
    return LLMClient(config)