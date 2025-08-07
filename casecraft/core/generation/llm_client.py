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
    """LLM API client implementation (currently using BigModel GLM-4.5-X)."""
    
    def __init__(self, config: LLMConfig):
        """Initialize BigModel client.
        
        Args:
            config: LLM configuration
        """
        self.config = config
        self.base_url = config.base_url or "https://open.bigmodel.cn/api/paas/v4"
        self._request_lock = asyncio.Lock()  # Ensure single concurrency
        self.logger = get_logger("llm_client")
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
            
            # Log request details for debugging
            self.logger.debug(f"LLM request - Model: {payload['model']}, Messages: {len(messages)} messages")
            self.logger.debug(f"LLM request payload keys: {list(payload.keys())}")
            
            try:
                response, retry_count = await self._make_request_with_retry("/chat/completions", payload)
                
                # Log successful response details
                self.logger.debug(f"LLM response received - Status: success, Retry count: {retry_count}")
                if response.get("usage"):
                    usage = response["usage"]
                    self.logger.debug(f"Token usage - Prompt: {usage.get('prompt_tokens', 0)}, "
                                    f"Completion: {usage.get('completion_tokens', 0)}, "
                                    f"Total: {usage.get('total_tokens', 0)}")
                
                choice = response["choices"][0]
                return LLMResponse(
                    content=choice["message"]["content"],
                    model=self.config.model or "glm-4.5-x",
                    usage=response.get("usage"),
                    finish_reason=choice.get("finish_reason"),
                    retry_count=retry_count
                )
                
            except Exception as e:
                # Log detailed error information
                self.logger.error(f"LLM request failed: {str(e)}")
                self.logger.debug(f"Request details - URL: {self.base_url}/chat/completions")
                self.logger.debug(f"Request payload (truncated): {str(payload)[:200]}...")
                raise LLMError(f"BigModel API error: {e}") from e
    
    async def _make_request_with_retry(
        self, 
        endpoint: str, 
        payload: Dict[str, Any]
    ) -> tuple[Dict[str, Any], int]:
        """Make HTTP request with smart retry logic.
        
        Args:
            endpoint: API endpoint
            payload: Request payload
            
        Returns:
            Tuple of (response data, retry count)
            
        Raises:
            LLMError: If request fails
            LLMRateLimitError: If rate limit exceeded
        """
        last_error = None
        base_wait = 2.0  # Base wait time in seconds
        
        for attempt in range(self.config.max_retries + 1):
            try:
                self.logger.debug(f"Attempting HTTP request (attempt {attempt + 1}/{self.config.max_retries + 1})")
                response = await self.client.post(endpoint, json=payload)
                
                # Log response status and headers for debugging
                self.logger.debug(f"HTTP response status: {response.status_code}")
                self.logger.debug(f"Response headers: {dict(response.headers)}")
                
                if response.status_code == 429:
                    # Rate limit hit - use exponential backoff with jitter
                    self.logger.warning(f"Rate limit hit (429) on attempt {attempt + 1}")
                    
                    if attempt < self.config.max_retries:
                        # Try to get retry-after header
                        retry_after = response.headers.get('retry-after')
                        if retry_after:
                            wait_time = float(retry_after) + (0.5 * attempt)
                            self.logger.debug(f"Using retry-after header: {retry_after}s + jitter")
                        else:
                            # Exponential backoff with jitter
                            wait_time = base_wait * (2 ** attempt) + (0.1 * attempt)
                            wait_time = min(wait_time, 60)  # Cap at 60 seconds
                            self.logger.debug(f"Using exponential backoff: {wait_time}s")
                        
                        self.logger.info(f"Waiting {wait_time:.2f}s before retry...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        error_msg = (
                            f"Rate limit exceeded after {self.config.max_retries} retries. "
                            f"BigModel only supports single concurrency."
                        )
                        self.logger.error(error_msg)
                        raise LLMRateLimitError(error_msg)
                
                response.raise_for_status()
                return response.json(), attempt  # Return response and retry count
                
            except httpx.HTTPStatusError as e:
                last_error = e
                status_code = e.response.status_code
                
                # Log detailed error information
                self.logger.error(f"HTTP status error {status_code}: {e}")
                try:
                    response_text = e.response.text
                    self.logger.debug(f"Response body: {response_text[:500]}...")
                except Exception:
                    self.logger.debug("Could not read response body")
                
                if status_code == 429:
                    # Already handled above
                    continue
                elif status_code >= 500:
                    # Server error - retry with backoff
                    self.logger.warning(f"Server error {status_code} on attempt {attempt + 1}, retrying...")
                    if attempt < self.config.max_retries:
                        wait_time = base_wait * (attempt + 1)
                        self.logger.info(f"Waiting {wait_time}s before retry...")
                        await asyncio.sleep(wait_time)
                        continue
                else:
                    # Client error - don't retry
                    error_msg = f"HTTP error {status_code}: {e}"
                    self.logger.error(f"Client error (no retry): {error_msg}")
                    raise LLMError(error_msg)
                    
            except httpx.RequestError as e:
                last_error = e
                self.logger.error(f"Network/request error on attempt {attempt + 1}: {e}")
                
                if attempt < self.config.max_retries:
                    # Network error - retry with backoff
                    wait_time = base_wait * (attempt + 1)
                    self.logger.info(f"Network error, waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                    continue
        
        # All retries exhausted
        error_msg = f"Request failed after {self.config.max_retries + 1} attempts: {last_error}"
        self.logger.error(f"All retry attempts exhausted: {error_msg}")
        raise LLMError(error_msg)
    
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