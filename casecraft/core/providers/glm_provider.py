"""GLM Provider implementation."""

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


class GLMProvider(LLMProvider):
    """智谱 GLM 提供商实现."""
    
    name = "glm"
    
    def __init__(self, config: ProviderConfig):
        """Initialize GLM provider.
        
        Args:
            config: Provider configuration
        """
        super().__init__(config)
        # BigModel API endpoint - use configured or default
        self.base_url = config.base_url
        if not self.base_url:
            # Use default if not configured
            self.base_url = "https://open.bigmodel.cn/api/paas/v4"
            self.logger.info(f"Using default base URL: {self.base_url}")
        self._request_lock = asyncio.Lock()  # Ensure single concurrency for GLM
        self.logger = get_logger(f"provider.{self.name}")
        
        # Check for 'think' feature in config extras
        self.think = config.extra.get('think', False) if hasattr(config, 'extra') else False
        
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=config.timeout,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json"
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
        """Generate response from GLM.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt
            progress_callback: Progress callback function
            **kwargs: Additional generation parameters
            
        Returns:
            LLM response
        """
        async with self._request_lock:  # GLM only supports single concurrency
            messages = []
            
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self.config.model,
                "messages": messages,
                "think": self.think,
                "stream": self.config.stream,
                "temperature": kwargs.get("temperature", self.config.temperature)
            }
            
            # Add structured output format if enabled
            if self.config.use_structured_output:
                payload["response_format"] = {"type": "json_object"}
            
            self.logger.debug(f"GLM request - Model: {payload['model']}, Messages: {len(messages)}")
            
            try:
                if self.config.stream and progress_callback:
                    return await self._generate_stream(messages, kwargs.get("temperature", self.config.temperature), progress_callback)
                else:
                    return await self._generate_non_stream(payload, progress_callback)
                    
            except Exception as e:
                self.logger.error(f"GLM generation failed: {str(e)}")
                raise ProviderGenerationError(f"GLM API error: {e}") from e
    
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
        # Update progress to 10% when starting
        if progress_callback:
            try:
                progress_callback(0.1)  # 10% - Starting request
                self.logger.debug("Progress update: 10% - Starting request")
            except Exception as e:
                self.logger.warning(f"Progress callback error: {e}")
        
        # Create async task for the actual request
        request_task = asyncio.create_task(
            self._make_request_with_retry("/chat/completions", payload, progress_callback)
        )
        
        # Simulate progress while waiting (10%-80%)
        if progress_callback:
            try:
                start_time = asyncio.get_event_loop().time()
                progress_update_interval = 0.5  # Update every 500ms
                
                while not request_task.done():
                    await asyncio.sleep(progress_update_interval)
                    elapsed = asyncio.get_event_loop().time() - start_time
                    
                    # Gradually increase progress from 10% to 80% over 60 seconds
                    progress_ratio = min(elapsed / 60, 1.0)
                    # Logarithmic progress curve
                    simulated_progress = 0.1 + (0.7 * (1 - (1 / (1 + progress_ratio * 9))))
                    simulated_progress = min(simulated_progress, 0.8)  # Cap at 80%
                    
                    progress_callback(simulated_progress)
                    self.logger.debug(f"Progress update: {simulated_progress:.1%} - Waiting for response")
            except Exception as e:
                self.logger.warning(f"Progress simulation error: {e}")
        
        # Get the response
        response, retry_count = await request_task
        
        # Update progress to 90% after receiving response
        if progress_callback:
            try:
                progress_callback(0.9)  # 90% - Processing response
                self.logger.debug("Progress update: 90% - Processing response")
            except Exception as e:
                self.logger.warning(f"Progress callback error: {e}")
        
        # Parse response
        choice = response["choices"][0]
        
        # Create token usage
        token_usage = None
        if response.get("usage"):
            usage_data = response["usage"]
            token_usage = TokenUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
                model=self.config.model
            )
        
        return LLMResponse(
            content=choice["message"]["content"],
            provider=self.name,
            model=self.config.model,
            token_usage=token_usage,
            metadata={
                "finish_reason": choice.get("finish_reason"),
                "retry_count": retry_count
            }
        )
    
    async def _generate_stream(
        self,
        messages: list,
        temperature: float,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> LLMResponse:
        """Generate response with streaming.
        
        Args:
            messages: Message list
            temperature: Temperature for generation
            progress_callback: Progress callback function
            
        Returns:
            LLM response
        """
        payload = {
            "model": self.config.model,
            "messages": messages,
            "think": self.think,
            "stream": True,
            "temperature": temperature
        }
        
        # Add structured output format if enabled
        if self.config.use_structured_output:
            payload["response_format"] = {"type": "json_object"}
        
        content_chunks = []
        token_usage = None
        finish_reason = None
        
        try:
            async with self.client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if not line or line.startswith(":"):
                        continue
                    
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix
                        
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            
                            if "choices" in data and data["choices"]:
                                choice = data["choices"][0]
                                delta = choice.get("delta", {})
                                
                                if "content" in delta:
                                    content_chunks.append(delta["content"])
                                    
                                    # Update progress based on content generation
                                    if progress_callback:
                                        # Estimate progress (20% to 90%)
                                        progress = 0.2 + min(len(content_chunks) / 100, 0.7)
                                        progress_callback(progress)
                                
                                if choice.get("finish_reason"):
                                    finish_reason = choice["finish_reason"]
                            
                            # Get usage data from final message
                            if "usage" in data:
                                usage_data = data["usage"]
                                token_usage = TokenUsage(
                                    prompt_tokens=usage_data.get("prompt_tokens", 0),
                                    completion_tokens=usage_data.get("completion_tokens", 0),
                                    total_tokens=usage_data.get("total_tokens", 0),
                                    model=self.config.model
                                )
                        except json.JSONDecodeError:
                            self.logger.warning(f"Failed to parse SSE data: {data_str}")
                            continue
                
                # Update to 100% when done
                if progress_callback:
                    progress_callback(1.0)
                
                return LLMResponse(
                    content="".join(content_chunks),
                    provider=self.name,
                    model=self.config.model,
                    token_usage=token_usage,
                    metadata={"finish_reason": finish_reason}
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
        # Read retry configuration from environment
        base_wait = float(os.getenv("CASECRAFT_GLM_RETRY_BASE_WAIT", "2.0"))
        max_wait = float(os.getenv("CASECRAFT_GLM_RETRY_MAX_WAIT", "60"))
        multiplier = float(os.getenv("CASECRAFT_GLM_RETRY_MULTIPLIER", "2"))
        current_progress = 0.1
        
        for attempt in range(self.config.max_retries + 1):
            try:
                self.logger.debug(f"Attempting request (attempt {attempt + 1}/{self.config.max_retries + 1})")
                response = await self.client.post(endpoint, json=payload)
                
                if response.status_code == 429:
                    # Rate limit hit
                    self.logger.warning(f"Rate limit hit (429) on attempt {attempt + 1}")
                    
                    if attempt < self.config.max_retries:
                        # Progress rollback on retry
                        if progress_callback:
                            current_progress = max(current_progress * 0.7, 0.1)
                            try:
                                progress_callback(current_progress)
                                self.logger.debug(f"Progress rollback on retry: {current_progress:.1%}")
                            except Exception as e:
                                self.logger.warning(f"Progress callback error during retry: {e}")
                        
                        # Handle retry-after header
                        retry_after = response.headers.get('retry-after')
                        if retry_after:
                            wait_time = float(retry_after) + (0.5 * attempt)
                        else:
                            wait_time = base_wait * (multiplier ** attempt) + (0.1 * attempt)
                            wait_time = min(wait_time, max_wait)
                        
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
            from casecraft.core.generation.llm_client import LLMClient
            
            # Create LLMClient with this provider (new simplified approach)
            llm_client = LLMClient(provider=self)
            self._test_generator = TestCaseGenerator(llm_client)
        
        # Use the test generator to create test cases
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
        max_workers = int(os.getenv("CASECRAFT_GLM_MAX_WORKERS", "1"))
        return min(self.config.workers, max_workers)
    
    def validate_config(self) -> bool:
        """Validate provider configuration.
        
        Returns:
            True if configuration is valid
        """
        if not self.config.api_key:
            self.logger.error("API key is required for GLM provider")
            return False
        
        if not self.config.model:
            self.logger.error("Model name is required for GLM provider")
            return False
        
        return True
    
    async def health_check(self) -> bool:
        """Check provider health.
        
        Returns:
            True if provider is healthy
        """
        try:
            # Try a simple generation request
            response = await self.generate(
                prompt="Hi",
                system_prompt="You are a helpful assistant. Reply with 'OK' only."
            )
            return bool(response.content)
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Clean up provider resources."""
        await self.client.aclose()
        self.logger.debug("GLM provider closed")