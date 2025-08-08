"""Qwen (通义千问) Provider implementation."""

import asyncio
import json
from typing import Any, Dict, Optional, Callable
import httpx

from casecraft.core.providers.base import LLMProvider, LLMResponse, ProviderConfig
from casecraft.core.providers.exceptions import (
    ProviderGenerationError,
    ProviderRateLimitError,
    ProviderConfigError
)
from casecraft.models.api_spec import APIEndpoint
from casecraft.models.test_case import TestCaseCollection
from casecraft.models.usage import TokenUsage
from casecraft.core.generation.test_generator import TestCaseGenerator
from casecraft.utils.logging import get_logger


class QwenProvider(LLMProvider):
    """阿里通义千问提供商实现."""
    
    name = "qwen"
    
    def __init__(self, config: ProviderConfig):
        """Initialize Qwen provider.
        
        Args:
            config: Provider configuration
        """
        super().__init__(config)
        # DashScope API endpoint
        self.base_url = config.base_url or "https://dashscope.aliyuncs.com/api/v1"
        self.logger = get_logger(f"provider.{self.name}")
        
        # Qwen supports up to 3 concurrent requests
        self._semaphore = asyncio.Semaphore(min(config.workers, 3))
        
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=config.timeout,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
                "X-DashScope-DataInspection": "disable"  # Disable data inspection for privacy
            }
        )
        
        # Test generator will be initialized lazily
        self._test_generator = None
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate response from Qwen.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt
            progress_callback: Progress callback function
            **kwargs: Additional generation parameters
            
        Returns:
            LLM response
        """
        async with self._semaphore:
            messages = []
            
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            messages.append({"role": "user", "content": prompt})
            
            # Qwen API payload format
            # OpenAI compatible format
            payload = {
                "model": self.config.model,  # e.g., "qwen-max", "qwen-plus", "qwen-turbo"
                "messages": messages,  # Direct messages, not nested in input
                "temperature": kwargs.get("temperature", self.config.temperature),
                "top_p": kwargs.get("top_p", 0.9),
                "max_tokens": kwargs.get("max_tokens", 2000),
                "stream": self.config.stream
            }
            
            self.logger.debug(f"Qwen request - Model: {self.config.model}, Messages: {len(messages)}")
            
            try:
                if self.config.stream and progress_callback:
                    return await self._generate_stream(payload, progress_callback)
                else:
                    return await self._generate_non_stream(payload, progress_callback)
                    
            except Exception as e:
                self.logger.error(f"Qwen generation failed: {str(e)}")
                raise ProviderGenerationError(f"Qwen API error: {e}") from e
    
    async def _generate_non_stream(
        self,
        payload: Dict[str, Any],
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> LLMResponse:
        """Generate response without streaming.
        
        Args:
            payload: Request payload
            progress_callback: Progress callback function
            
        Returns:
            LLM response
        """
        # Update progress
        if progress_callback:
            try:
                progress_callback(0.1)  # 10% - Starting
                self.logger.debug("Progress update: 10% - Starting request")
            except Exception as e:
                self.logger.warning(f"Progress callback error: {e}")
        
        # Make request to OpenAI compatible endpoint
        response, retry_count = await self._make_request_with_retry(
            "/chat/completions",
            payload,
            progress_callback
        )
        
        # Update progress
        if progress_callback:
            try:
                progress_callback(0.9)  # 90% - Processing
                self.logger.debug("Progress update: 90% - Processing response")
            except Exception as e:
                self.logger.warning(f"Progress callback error: {e}")
        
        # Parse OpenAI format response
        choices = response.get("choices", [])
        usage = response.get("usage", {})
        
        # Extract content from first choice
        content = ""
        finish_reason = None
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")
            finish_reason = choices[0].get("finish_reason")
        
        # Create token usage (OpenAI format)
        token_usage = None
        if usage:
            token_usage = TokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                model=self.config.model
            )
        
        # Update to 100%
        if progress_callback:
            try:
                progress_callback(1.0)
            except Exception as e:
                self.logger.warning(f"Progress callback error: {e}")
        
        return LLMResponse(
            content=content,
            provider=self.name,
            model=self.config.model,
            token_usage=token_usage,
            metadata={
                "finish_reason": finish_reason,
                "retry_count": retry_count,
                "request_id": response.get("id")
            }
        )
    
    async def _generate_stream(
        self,
        payload: Dict[str, Any],
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> LLMResponse:
        """Generate response with streaming.
        
        Args:
            payload: Request payload
            progress_callback: Progress callback function
            
        Returns:
            LLM response
        """
        # Streaming is enabled in the payload already
        
        content_chunks = []
        token_usage = None
        finish_reason = None
        request_id = None
        
        try:
            # Qwen uses SSE (Server-Sent Events) for streaming
            headers = dict(self.client.headers)
            headers["Accept"] = "text/event-stream"
            
            async with self.client.stream(
                "POST",
                "/chat/completions",
                json=payload,
                headers=headers
            ) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    
                    # Parse SSE format
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            
                            # Extract content from OpenAI format
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                if "content" in delta:
                                    # In streaming mode, each message contains incremental text
                                    content_chunks.append(delta["content"])
                                    
                                    # Update progress
                                    if progress_callback:
                                        progress = 0.2 + min(len(content_chunks) / 100, 0.7)
                                        progress_callback(progress)
                                
                                # Get finish reason from last message
                                if choices[0].get("finish_reason"):
                                    finish_reason = choices[0]["finish_reason"]
                            
                            # Get usage data (OpenAI format)
                            if "usage" in data:
                                usage_data = data["usage"]
                                token_usage = TokenUsage(
                                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                                    completion_tokens=usage_data.get("completion_tokens", 0),
                                    total_tokens=usage_data.get("total_tokens", 0),
                                    model=self.config.model
                                )
                            
                            # Get request ID
                            if "id" in data:
                                request_id = data["id"]
                                
                        except json.JSONDecodeError:
                            self.logger.warning(f"Failed to parse SSE data: {data_str}")
                            continue
                
                # Update to 100%
                if progress_callback:
                    progress_callback(1.0)
                
                return LLMResponse(
                    content="".join(content_chunks),
                    provider=self.name,
                    model=self.config.model,
                    token_usage=token_usage,
                    metadata={
                        "finish_reason": finish_reason,
                        "request_id": request_id
                    }
                )
                
        except Exception as e:
            self.logger.error(f"Streaming generation failed: {e}")
            raise ProviderGenerationError(f"Streaming failed: {e}") from e
    
    async def _make_request_with_retry(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> tuple[Dict[str, Any], int]:
        """Make HTTP request with retry logic.
        
        Args:
            endpoint: API endpoint
            payload: Request payload
            progress_callback: Progress callback function
            
        Returns:
            Tuple of (response data, retry count)
        """
        last_error = None
        base_wait = 1.0  # Qwen has lower rate limits, start with 1 second
        
        for attempt in range(self.config.max_retries + 1):
            try:
                self.logger.debug(f"Attempting request (attempt {attempt + 1}/{self.config.max_retries + 1})")
                response = await self.client.post(endpoint, json=payload)
                
                # Check for rate limiting
                if response.status_code == 429:
                    self.logger.warning(f"Rate limit hit on attempt {attempt + 1}")
                    
                    if attempt < self.config.max_retries:
                        # Exponential backoff
                        wait_time = base_wait * (2 ** attempt)
                        wait_time = min(wait_time, 30)  # Cap at 30 seconds
                        
                        self.logger.info(f"Waiting {wait_time:.2f}s before retry...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise ProviderRateLimitError(
                            f"Rate limit exceeded after {self.config.max_retries} retries"
                        )
                
                response.raise_for_status()
                return response.json(), attempt
                
            except httpx.HTTPStatusError as e:
                last_error = e
                status_code = e.response.status_code
                
                self.logger.error(f"HTTP status error {status_code}: {e}")
                
                if status_code >= 500 and attempt < self.config.max_retries:
                    # Server error - retry
                    wait_time = base_wait * (attempt + 1)
                    self.logger.info(f"Server error, waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise ProviderGenerationError(f"HTTP error {status_code}: {e}")
                    
            except httpx.RequestError as e:
                last_error = e
                self.logger.error(f"Network error on attempt {attempt + 1}: {e}")
                
                if attempt < self.config.max_retries:
                    wait_time = base_wait * (attempt + 1)
                    self.logger.info(f"Network error, waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                    continue
        
        # All retries exhausted
        raise ProviderGenerationError(
            f"Request failed after {self.config.max_retries + 1} attempts: {last_error}"
        )
    
    async def generate_test_cases(
        self,
        endpoint: APIEndpoint,
        progress_callback: Optional[Callable[[float], None]] = None,
        **kwargs
    ) -> tuple[TestCaseCollection, Optional[TokenUsage]]:
        """Generate test cases for an API endpoint.
        
        Args:
            endpoint: API endpoint
            progress_callback: Progress callback function
            **kwargs: Additional generation parameters
            
        Returns:
            Tuple of (test cases, token usage)
        """
        # Initialize test generator if needed
        if not self._test_generator:
            # Create a wrapper for compatibility
            from casecraft.core.generation.llm_client import LLMClient
            from casecraft.models.config import LLMConfig
            
            # Convert provider config to LLM config
            llm_config = LLMConfig(
                model=self.config.model,
                api_key=self.config.api_key,
                base_url=self.base_url,
                timeout=self.config.timeout,
                max_retries=self.config.max_retries,
                temperature=self.config.temperature,
                stream=self.config.stream
            )
            
            # Create a custom LLM client that uses this provider
            class QwenLLMClient(LLMClient):
                def __init__(self, config, provider):
                    super().__init__(config)
                    self.provider = provider
                
                async def generate(self, prompt, system_prompt=None, progress_callback=None, **kwargs):
                    response = await self.provider.generate(
                        prompt, system_prompt, progress_callback, **kwargs
                    )
                    # Convert to LLMClient response format
                    from casecraft.core.generation.llm_client import LLMResponse as ClientResponse
                    return ClientResponse(
                        content=response.content,
                        model=response.model,
                        usage=response.token_usage.__dict__ if response.token_usage else None,
                        finish_reason=response.metadata.get("finish_reason"),
                        retry_count=response.metadata.get("retry_count", 0)
                    )
            
            llm_client = QwenLLMClient(llm_config, self)
            self._test_generator = TestCaseGenerator(llm_client)
        
        # Generate test cases
        result = await self._test_generator.generate_test_cases(
            endpoint,
            progress_callback=progress_callback
        )
        
        return result.test_cases, result.token_usage
    
    def get_max_workers(self) -> int:
        """Get maximum concurrent workers.
        
        Returns:
            Maximum number of concurrent workers (3 for Qwen)
        """
        return min(self.config.workers, 3)  # Qwen supports up to 3 concurrent requests
    
    def validate_config(self) -> bool:
        """Validate provider configuration.
        
        Returns:
            True if configuration is valid
        """
        if not self.config.api_key:
            self.logger.error("API key is required for Qwen provider")
            return False
        
        if not self.config.model:
            self.logger.error("Model name is required for Qwen provider")
            return False
        
        # Validate model name
        valid_models = ["qwen-max", "qwen-plus", "qwen-turbo", "qwen-max-longcontext"]
        if not any(self.config.model.startswith(m) for m in valid_models):
            self.logger.warning(f"Unknown Qwen model: {self.config.model}")
        
        return True
    
    async def health_check(self) -> bool:
        """Check provider health.
        
        Returns:
            True if provider is healthy
        """
        try:
            # Try a simple generation request
            response = await self.generate(
                prompt="Hello",
                system_prompt="Reply with 'OK' only."
            )
            return bool(response.content)
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Clean up provider resources."""
        await self.client.aclose()
        self.logger.debug("Qwen provider closed")