"""Qwen (通义千问) Provider implementation."""

import asyncio
import json
import os
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
from casecraft.utils.constants import HTTP_RATE_LIMIT, HTTP_SERVER_ERRORS


class QwenProvider(LLMProvider):
    """阿里通义千问提供商实现."""
    
    name = "qwen"
    
    def __init__(self, config: ProviderConfig):
        """Initialize Qwen provider.
        
        Args:
            config: Provider configuration
        """
        super().__init__(config)
        # DashScope API endpoint - use configured or default
        self.base_url = config.base_url
        if not self.base_url:
            # Use default if not configured
            self.base_url = "https://dashscope.aliyuncs.com/api/v1"
            self.logger.info(f"Using default base URL: {self.base_url}")
        self.logger = get_logger(f"provider.{self.name}")
        
        # Configure concurrent requests from environment
        max_workers = int(os.getenv("CASECRAFT_QWEN_MAX_WORKERS", "3"))
        self._semaphore = asyncio.Semaphore(min(config.workers, max_workers))
        
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
                "top_p": kwargs.get("top_p", float(os.getenv("CASECRAFT_DEFAULT_TOP_P", "0.9"))),
                "max_tokens": kwargs.get("max_tokens", int(os.getenv("CASECRAFT_DEFAULT_MAX_TOKENS", "8192"))),
                "stream": self.config.stream
            }
            
            # Add stream_options to get token usage in streaming mode
            if self.config.stream:
                payload["stream_options"] = {"include_usage": True}
            
            # Add structured output format if enabled
            if self.config.use_structured_output:
                payload["response_format"] = {"type": "json_object"}
            
            self.logger.debug(f"Qwen request - Model: {self.config.model}, Messages: {len(messages)}")
            
            try:
                if self.config.stream and progress_callback:
                    return await self._generate_stream(payload, progress_callback)
                else:
                    return await self._generate_non_stream(payload, progress_callback)
                    
            except Exception as e:
                # Convert to friendly error
                friendly_error = self.create_friendly_error(e, {
                    "model": self.config.model,
                    "stream": self.config.stream,
                    "messages": payload.get("messages", [])
                })
                self.logger.error(f"Qwen generation failed: {friendly_error.get_friendly_message()}")
                raise friendly_error from e
    
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
        if choices and len(choices) > 0 and choices[0] is not None:
            choice = choices[0]
            if isinstance(choice, dict):
                message = choice.get("message", {})
                content = message.get("content", "")
                finish_reason = choice.get("finish_reason")
        
        # Create token usage (OpenAI format)
        token_usage = None
        if usage:
            token_usage = TokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                model=self.config.model
            )
        
        # Calculate final provider progress based on actual response
        if progress_callback:
            try:
                final_progress = self.calculate_provider_progress(
                    base_progress=0.9,  # Base from processing phase
                    content_length=len(content) if content else 0,
                    has_finish_reason=bool(finish_reason),
                    is_streaming=False,
                    retry_count=retry_count
                )
                progress_callback(final_progress)
            except Exception as e:
                self.logger.warning(f"Progress callback error: {e}")
        
        self.logger.info(f"Qwen returning token_usage: {token_usage}")
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
                            
                            # Safely extract content from OpenAI format
                            choices = data.get("choices", []) if isinstance(data, dict) else []
                            if choices and len(choices) > 0 and choices[0] is not None:
                                choice = choices[0]
                                if isinstance(choice, dict):
                                    delta = choice.get("delta", {})
                                    if isinstance(delta, dict) and "content" in delta:
                                        # In streaming mode, each message contains incremental text
                                        content_chunks.append(delta["content"])
                                        
                                        # Update progress
                                        if progress_callback:
                                            try:
                                                progress = 0.2 + min(len(content_chunks) / 100, 0.7)
                                                progress_callback(progress)
                                            except Exception as cb_err:
                                                self.logger.warning(f"Progress callback error: {cb_err}")
                                    
                                    # Get finish reason from last message
                                    finish_reason_value = choice.get("finish_reason")
                                    if finish_reason_value:
                                        finish_reason = finish_reason_value
                            
                            # Get usage data (OpenAI format) - safely
                            if isinstance(data, dict) and "usage" in data:
                                usage_data = data["usage"]
                                if isinstance(usage_data, dict):
                                    token_usage = TokenUsage(
                                        prompt_tokens=usage_data.get("prompt_tokens", 0),
                                        completion_tokens=usage_data.get("completion_tokens", 0),
                                        total_tokens=usage_data.get("total_tokens", 0),
                                        model=self.config.model
                                    )
                                    self.logger.info(f"Found token usage in stream: {token_usage}")
                            
                            # Get request ID - safely
                            if isinstance(data, dict) and "id" in data:
                                request_id = data["id"]
                                
                        except json.JSONDecodeError as json_err:
                            self.logger.warning(f"Failed to parse SSE data: {data_str[:100]}... Error: {json_err}")
                            continue
                        except Exception as parse_err:
                            self.logger.error(f"Error processing streaming data: {parse_err}, Data type: {type(data)}")
                            continue
                
                # Calculate final provider progress based on actual response
                final_content = "".join(content_chunks)
                if progress_callback:
                    try:
                        final_progress = self.calculate_provider_progress(
                            base_progress=0.9,  # Base from streaming
                            content_length=len(final_content),
                            has_finish_reason=bool(finish_reason),
                            is_streaming=True,
                            retry_count=0  # Streaming doesn't use retry mechanism
                        )
                        progress_callback(final_progress)
                    except Exception as cb_err:
                        self.logger.warning(f"Final progress callback error: {cb_err}")
                
                self.logger.info(f"Qwen streaming returning token_usage: {token_usage}")
                return LLMResponse(
                    content=final_content,
                    provider=self.name,
                    model=self.config.model,
                    token_usage=token_usage,
                    metadata={
                        "finish_reason": finish_reason,
                        "request_id": request_id
                    }
                )
                
        except Exception as e:
            self.logger.error(f"Streaming generation failed: {e}, Error type: {type(e).__name__}")
            # Convert to friendly error
            friendly_error = self.create_friendly_error(e, {
                "model": self.config.model,
                "stream": True,
                "messages": payload.get("messages", [])
            })
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            self.logger.error(f"Streaming generation failed: {friendly_error.get_friendly_message()}")
            raise friendly_error from e
    
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
        # Read retry configuration from environment
        base_wait = float(os.getenv("CASECRAFT_QWEN_RETRY_BASE_WAIT", "1.0"))
        max_wait = float(os.getenv("CASECRAFT_QWEN_RETRY_MAX_WAIT", "30"))
        multiplier = float(os.getenv("CASECRAFT_QWEN_RETRY_MULTIPLIER", "2"))
        
        for attempt in range(self.config.max_retries + 1):
            try:
                self.logger.debug(f"Attempting request (attempt {attempt + 1}/{self.config.max_retries + 1})")
                response = await self.client.post(endpoint, json=payload)
                
                # Check for rate limiting
                if response.status_code == HTTP_RATE_LIMIT:
                    self.logger.warning(f"Rate limit hit on attempt {attempt + 1}")
                    
                    if attempt < self.config.max_retries:
                        # Exponential backoff with configurable multiplier
                        wait_time = base_wait * (multiplier ** attempt)
                        wait_time = min(wait_time, max_wait)  # Cap at max_wait
                        
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
                
                if status_code in HTTP_SERVER_ERRORS and attempt < self.config.max_retries:
                    # Server error - retry
                    wait_time = base_wait * (attempt + 1)
                    self.logger.info(f"Server error, waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    friendly_error = self.create_friendly_error(e)
                    raise friendly_error
                    
            except httpx.RequestError as e:
                last_error = e
                self.logger.error(f"Network error on attempt {attempt + 1}: {e}")
                
                if attempt < self.config.max_retries:
                    wait_time = base_wait * (attempt + 1)
                    self.logger.info(f"Network error, waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                    continue
        
        # All retries exhausted
        # Convert to friendly error
        friendly_error = self.create_friendly_error(last_error or Exception("Request failed after retries"))
        raise friendly_error
    
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
            
            # Create LLMClient with this provider (new simplified approach)
            llm_client = LLMClient(provider=self)
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
            Maximum number of concurrent workers
        """
        # Read from environment variable with default fallback
        max_workers = int(os.getenv("CASECRAFT_QWEN_MAX_WORKERS", "3"))
        return min(self.config.workers, max_workers)
    
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
        
        # Log the model being used (no validation - let API handle it)
        self.logger.info(f"Using Qwen model: {self.config.model}")
        
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