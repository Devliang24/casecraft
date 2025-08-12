"""Kimi (Moonshot) Provider implementation."""

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


class KimiProvider(LLMProvider):
    """Moonshot Kimi 提供商实现 (OpenAI 兼容接口)."""
    
    name = "kimi"
    
    def __init__(self, config: ProviderConfig):
        """Initialize Kimi provider.
        
        Args:
            config: Provider configuration
        """
        super().__init__(config)
        # Kimi uses OpenAI-compatible API
        self.base_url = config.base_url or "https://api.moonshot.cn/v1"
        self.logger = get_logger(f"provider.{self.name}")
        
        # Kimi supports up to 2 concurrent requests
        self._semaphore = asyncio.Semaphore(min(config.workers, 2))
        
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
        """Generate response from Kimi.
        
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
            
            # OpenAI-compatible payload format
            payload = {
                "model": self.config.model,  # e.g., "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"
                "messages": messages,
                "temperature": kwargs.get("temperature", self.config.temperature),
                "top_p": kwargs.get("top_p", 1.0),
                "max_tokens": kwargs.get("max_tokens", 2000),
                "stream": self.config.stream
            }
            
            # Add structured output format if enabled
            # Note: Kimi's structured output wraps arrays in an object, 
            # which breaks our test case parsing. Disable for now.
            # if self.config.use_structured_output:
            #     payload["response_format"] = {"type": "json_object"}
            
            self.logger.debug(f"Kimi request - Model: {self.config.model}, Messages: {len(messages)}")
            
            try:
                if self.config.stream and progress_callback:
                    return await self._generate_stream(payload, progress_callback)
                else:
                    return await self._generate_non_stream(payload, progress_callback)
                    
            except Exception as e:
                self.logger.error(f"Kimi generation failed: {str(e)}")
                raise ProviderGenerationError(f"Kimi API error: {e}") from e
    
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
        
        # Simulate progress while waiting
        request_task = asyncio.create_task(
            self._make_request_with_retry("/chat/completions", payload, progress_callback)
        )
        
        if progress_callback:
            try:
                start_time = asyncio.get_event_loop().time()
                
                while not request_task.done():
                    await asyncio.sleep(0.5)
                    elapsed = asyncio.get_event_loop().time() - start_time
                    
                    # Logarithmic progress curve
                    progress_ratio = min(elapsed / 30, 1.0)
                    simulated_progress = 0.1 + (0.7 * (1 - (1 / (1 + progress_ratio * 9))))
                    simulated_progress = min(simulated_progress, 0.8)
                    
                    progress_callback(simulated_progress)
                    self.logger.debug(f"Progress update: {simulated_progress:.1%} - Waiting")
            except Exception as e:
                self.logger.warning(f"Progress simulation error: {e}")
        
        # Get response
        response, retry_count = await request_task
        
        # Update progress
        if progress_callback:
            try:
                progress_callback(0.9)  # 90% - Processing
                self.logger.debug("Progress update: 90% - Processing response")
            except Exception as e:
                self.logger.warning(f"Progress callback error: {e}")
        
        # Parse OpenAI-format response
        choice = response["choices"][0]
        usage = response.get("usage", {})
        
        # Create token usage
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
            content=choice["message"]["content"],
            provider=self.name,
            model=self.config.model,
            token_usage=token_usage,
            metadata={
                "finish_reason": choice.get("finish_reason"),
                "retry_count": retry_count,
                "id": response.get("id"),
                "object": response.get("object")
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
        content_chunks = []
        token_usage = None
        finish_reason = None
        response_id = None
        
        try:
            # OpenAI-compatible SSE streaming
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
                            
                            # Extract content from delta
                            if "choices" in data and data["choices"]:
                                choice = data["choices"][0]
                                delta = choice.get("delta", {})
                                
                                if "content" in delta:
                                    content_chunks.append(delta["content"])
                                    
                                    # Update progress
                                    if progress_callback:
                                        progress = 0.2 + min(len(content_chunks) / 100, 0.7)
                                        progress_callback(progress)
                                
                                if choice.get("finish_reason"):
                                    finish_reason = choice["finish_reason"]
                            
                            # Get response ID
                            if "id" in data:
                                response_id = data["id"]
                            
                            # Note: Kimi doesn't provide token usage in streaming mode
                            # We'll estimate it based on content length
                            
                        except json.JSONDecodeError:
                            self.logger.warning(f"Failed to parse SSE data: {data_str}")
                            continue
                
                # Update to 100%
                if progress_callback:
                    progress_callback(1.0)
                
                # Estimate token usage for streaming (rough approximation)
                content = "".join(content_chunks)
                estimated_tokens = len(content) // 4  # Rough estimate: 1 token ≈ 4 characters
                token_usage = TokenUsage(
                    prompt_tokens=len(str(payload["messages"])) // 4,
                    completion_tokens=estimated_tokens,
                    total_tokens=len(str(payload["messages"])) // 4 + estimated_tokens,
                    model=self.config.model
                )
                
                return LLMResponse(
                    content=content,
                    provider=self.name,
                    model=self.config.model,
                    token_usage=token_usage,
                    metadata={
                        "finish_reason": finish_reason,
                        "id": response_id,
                        "stream": True
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
        base_wait = 1.5  # Kimi has moderate rate limits
        
        for attempt in range(self.config.max_retries + 1):
            try:
                self.logger.debug(f"Attempting request (attempt {attempt + 1}/{self.config.max_retries + 1})")
                response = await self.client.post(endpoint, json=payload)
                
                # Check for rate limiting
                if response.status_code == 429:
                    self.logger.warning(f"Rate limit hit on attempt {attempt + 1}")
                    
                    if attempt < self.config.max_retries:
                        # Check for Retry-After header (OpenAI standard)
                        retry_after = response.headers.get('retry-after')
                        if retry_after:
                            wait_time = float(retry_after)
                        else:
                            # Exponential backoff
                            wait_time = base_wait * (2 ** attempt)
                            wait_time = min(wait_time, 45)  # Cap at 45 seconds
                        
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
                
                # Try to get error details from response
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get("error", {}).get("message", str(e))
                    self.logger.error(f"API error message: {error_msg}")
                except:
                    pass
                
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
            class KimiLLMClient(LLMClient):
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
            
            llm_client = KimiLLMClient(llm_config, self)
            self._test_generator = TestCaseGenerator(llm_client)
        
        # Generate test cases
        max_retries = 2  # Allow up to 2 retries if not enough test cases
        for retry in range(max_retries + 1):
            result = await self._test_generator.generate_test_cases(
                endpoint,
                progress_callback=progress_callback
            )
            
            # Check if we have minimum required test cases
            test_count = len(result.test_cases.test_cases) if hasattr(result.test_cases, 'test_cases') else 0
            
            if test_count >= 5:
                # Sufficient test cases generated
                return result.test_cases, result.token_usage
            elif retry < max_retries:
                # Not enough test cases, log warning and retry
                self.logger.warning(
                    f"Kimi generated only {test_count} test cases for {endpoint.get_endpoint_id()}, "
                    f"minimum 5 required. Retrying ({retry + 1}/{max_retries})..."
                )
                # Add a small delay before retry
                await asyncio.sleep(2)
            else:
                # Final attempt still insufficient, log error but return what we have
                self.logger.error(
                    f"Kimi could only generate {test_count} test cases for {endpoint.get_endpoint_id()} "
                    f"after {max_retries} retries. Minimum 5 required. Proceeding with partial results."
                )
                return result.test_cases, result.token_usage
        
        # Fallback (should not reach here)
        return result.test_cases, result.token_usage
    
    def get_max_workers(self) -> int:
        """Get maximum concurrent workers.
        
        Returns:
            Maximum number of concurrent workers (2 for Kimi)
        """
        return min(self.config.workers, 2)  # Kimi supports up to 2 concurrent requests
    
    def validate_config(self) -> bool:
        """Validate provider configuration.
        
        Returns:
            True if configuration is valid
        """
        if not self.config.api_key:
            self.logger.error("API key is required for Kimi provider")
            return False
        
        if not self.config.model:
            self.logger.error("Model name is required for Kimi provider")
            return False
        
        # Validate model name
        valid_models = ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]
        if self.config.model not in valid_models:
            self.logger.warning(f"Unknown Kimi model: {self.config.model}. Valid models: {valid_models}")
        
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
                system_prompt="Reply with 'OK' only."
            )
            return bool(response.content)
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Clean up provider resources."""
        await self.client.aclose()
        self.logger.debug("Kimi provider closed")