"""Kimi (Moonshot) Provider implementation."""

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


class KimiProvider(LLMProvider):
    """Moonshot Kimi 提供商实现 (OpenAI 兼容接口)."""
    
    name = "kimi"
    
    def __init__(self, config: ProviderConfig):
        """Initialize Kimi provider.
        
        Args:
            config: Provider configuration
        """
        super().__init__(config)
        # Kimi uses OpenAI-compatible API - use configured or default
        self.base_url = config.base_url
        if not self.base_url:
            # Use default if not configured
            self.base_url = "https://api.moonshot.cn/v1"
            self.logger.info(f"Using default base URL: {self.base_url}")
        self.logger = get_logger(f"provider.{self.name}")
        
        # Configure concurrent requests from environment
        max_workers = int(os.getenv("CASECRAFT_KIMI_MAX_WORKERS", "2"))
        self._semaphore = asyncio.Semaphore(min(config.workers, max_workers))
        
        # Set a reasonable default timeout for HTTP client
        # Individual requests can override this
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),  # 30s total, 10s connect
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
                "top_p": kwargs.get("top_p", float(os.getenv("CASECRAFT_DEFAULT_TOP_P", "1.0"))),
                "max_tokens": kwargs.get("max_tokens", int(os.getenv("CASECRAFT_DEFAULT_MAX_TOKENS", "2000"))),
                "stream": self.config.stream
            }
            
            # Add structured output format if enabled
            # Note: Kimi's structured output wraps arrays in an object, 
            # but we handle this with _unwrap_array_response method
            if self.config.use_structured_output:
                payload["response_format"] = {"type": "json_object"}
            
            self.logger.debug(f"Kimi request - Model: {self.config.model}, Messages: {len(messages)}")
            
            try:
                if self.config.stream and progress_callback:
                    return await self._generate_stream(payload, progress_callback)
                else:
                    return await self._generate_non_stream(payload, progress_callback)
                    
            except Exception as e:
                self.logger.error(f"Kimi generation failed: {str(e)}")
                raise ProviderGenerationError(f"Kimi API error: {e}") from e
    
    def _unwrap_array_response(self, content: str) -> str:
        """Unwrap array response from Kimi's structured output format.
        
        When using structured output (response_format), Kimi wraps arrays 
        in an object like {"response": [...]}. This method unwraps it.
        
        Args:
            content: Response content from Kimi
            
        Returns:
            Unwrapped content (array as string) or original content
        """
        # Log the raw content for debugging
        content_preview = content[:500] if len(content) > 500 else content
        self.logger.info(f"[Kimi] Unwrapping response, length: {len(content)}")
        self.logger.debug(f"[Kimi] Raw response preview: {content_preview}...")
        
        # Save debug response if enabled
        if os.getenv("CASECRAFT_DEBUG_KIMI"):
            import time
            debug_file = f"kimi_response_{int(time.time())}.json"
            try:
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.logger.info(f"[Kimi] Debug response saved to {debug_file}")
            except Exception as e:
                self.logger.warning(f"[Kimi] Failed to save debug response: {e}")
        
        try:
            parsed = json.loads(content)
            self.logger.debug(f"[Kimi] Parsed response type: {type(parsed)}")
            
            # If it's already an array, return as is
            if isinstance(parsed, list):
                self.logger.info(f"[Kimi] Response is already array with {len(parsed)} items")
                return content
            
            # If it's a dict, check for wrapped array
            if isinstance(parsed, dict):
                self.logger.debug(f"[Kimi] Response is dict with keys: {list(parsed.keys())}")
                
                # Check common wrapper keys that Kimi might use
                wrapper_keys = [
                    'response', 'data', 'result', 'test_cases', 'tests', 'items', 
                    'testCases', 'test_case_list', 'cases', 'array', 'list',
                    'content', 'output', 'generated', 'testdata'
                ]
                
                for key in wrapper_keys:
                    if key in parsed and isinstance(parsed[key], list):
                        # Found wrapped array, unwrap it
                        unwrapped = parsed[key]
                        self.logger.info(f"[Kimi] Unwrapped array from '{key}' field: {len(unwrapped)} items")
                        return json.dumps(unwrapped, ensure_ascii=False, indent=2)
                
                # Check if the entire dict looks like a single test case
                test_case_indicators = [
                    'test_id', 'id', 'test_name', 'name', 'method', 'path', 
                    'description', 'expected_status', 'headers', 'body',
                    'testId', 'testName', 'expectedStatus'
                ]
                
                if any(key in parsed for key in test_case_indicators):
                    self.logger.info("[Kimi] Single test case detected, wrapping in array")
                    return json.dumps([parsed], ensure_ascii=False, indent=2)
                
                # Check if there are nested objects that might contain arrays
                for key, value in parsed.items():
                    if isinstance(value, dict):
                        for nested_key in wrapper_keys:
                            if nested_key in value and isinstance(value[nested_key], list):
                                unwrapped = value[nested_key]
                                self.logger.info(f"[Kimi] Found nested array at '{key}.{nested_key}': {len(unwrapped)} items")
                                return json.dumps(unwrapped, ensure_ascii=False, indent=2)
                
                # Last resort: check if any value is a list
                for key, value in parsed.items():
                    if isinstance(value, list) and len(value) > 0:
                        # Check if it looks like test cases
                        first_item = value[0]
                        if isinstance(first_item, dict) and any(indicator in first_item for indicator in test_case_indicators):
                            self.logger.info(f"[Kimi] Found test case array at '{key}': {len(value)} items")
                            return json.dumps(value, ensure_ascii=False, indent=2)
                
                # Log all keys for debugging
                self.logger.warning(f"[Kimi] Could not find array in dict with keys: {list(parsed.keys())}")
            
            # If it's a string, maybe it's double-encoded JSON
            if isinstance(parsed, str):
                self.logger.debug("[Kimi] Response is string, checking for double-encoded JSON")
                try:
                    double_parsed = json.loads(parsed)
                    if isinstance(double_parsed, list):
                        self.logger.info(f"[Kimi] Found double-encoded JSON array with {len(double_parsed)} items")
                        return json.dumps(double_parsed, ensure_ascii=False, indent=2)
                except json.JSONDecodeError:
                    pass
            
            # Return original content if no unwrapping needed
            self.logger.warning("[Kimi] No unwrapping applied - returning original content")
            return content
            
        except json.JSONDecodeError as e:
            # If can't parse, return original content
            self.logger.warning(f"[Kimi] Content is not valid JSON: {e}")
            self.logger.debug(f"[Kimi] Invalid JSON content: {content[:200]}...")
            return content
        except Exception as e:
            # Any other error, return original content
            self.logger.error(f"[Kimi] Error unwrapping array response: {e}")
            return content
    
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
        
        # Get content and unwrap if structured output is enabled
        content = choice["message"]["content"]
        if self.config.use_structured_output:
            content = self._unwrap_array_response(content)
            self.logger.debug("Applied array unwrapping for structured output")
        
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
            content=content,
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
                
                # Combine chunks and unwrap if structured output is enabled
                content = "".join(content_chunks)
                if self.config.use_structured_output:
                    content = self._unwrap_array_response(content)
                    self.logger.debug("Applied array unwrapping for structured output (streaming)")
                
                # Estimate token usage for streaming (rough approximation)
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
        # Read retry configuration from environment
        base_wait = float(os.getenv("CASECRAFT_KIMI_RETRY_BASE_WAIT", "1.5"))
        max_wait = float(os.getenv("CASECRAFT_KIMI_RETRY_MAX_WAIT", "10"))  # Reduced from 45
        multiplier = float(os.getenv("CASECRAFT_KIMI_RETRY_MULTIPLIER", "2"))
        
        # Track total time to prevent excessive retries
        import time
        start_time = time.time()
        max_total_time = 45  # Maximum 45 seconds for all retries
        
        for attempt in range(self.config.max_retries + 1):
            # Check if we've exceeded total time limit
            if time.time() - start_time > max_total_time:
                self.logger.error(f"[Kimi] Exceeded maximum retry time of {max_total_time}s")
                raise ProviderGenerationError(f"Request timeout after {max_total_time}s")
            try:
                self.logger.info(f"[Kimi] Sending request to {endpoint} (attempt {attempt + 1}/{self.config.max_retries + 1})")
                self.logger.debug(f"[Kimi] Request payload size: {len(json.dumps(payload))} bytes")
                
                # Add timeout to individual request (25s to leave room for retries)
                response = await self.client.post(
                    endpoint, 
                    json=payload, 
                    timeout=httpx.Timeout(25.0, connect=5.0)
                )
                
                self.logger.info(f"[Kimi] Received response with status {response.status_code}")
                
                # Check for rate limiting
                if response.status_code == 429:
                    self.logger.warning(f"Rate limit hit on attempt {attempt + 1}")
                    
                    if attempt < self.config.max_retries:
                        # Check for Retry-After header (OpenAI standard)
                        retry_after = response.headers.get('retry-after')
                        if retry_after:
                            wait_time = float(retry_after)
                        else:
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
                self.logger.info(f"[Kimi] Parsing JSON response...")
                json_response = response.json()
                self.logger.info(f"[Kimi] Successfully parsed response")
                return json_response, attempt
                
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
            from casecraft.core.generation.llm_client import LLMClient
            from casecraft.core.generation.test_generator import TestCaseGenerator
            
            # Create LLMClient with this provider (new simplified approach)
            llm_client = LLMClient(provider=self)
            self._test_generator = TestCaseGenerator(llm_client)
        
        # Wrap the generation logic with timeout
        async def _generate_with_retries():
            # Generate test cases
            max_retries = 2  # Allow up to 2 retries if not enough test cases
            endpoint_id = endpoint.get_endpoint_id()
            
            self.logger.info(f"[Kimi] Starting generation for {endpoint_id}")
            
            for retry in range(max_retries + 1):
                self.logger.info(f"[Kimi] Attempt {retry + 1}/{max_retries + 1} for {endpoint_id}")
                
                try:
                    result = await self._test_generator.generate_test_cases(
                        endpoint,
                        progress_callback=progress_callback
                    )
                    
                    # Check if we have minimum required test cases
                    test_count = len(result.test_cases.test_cases) if hasattr(result.test_cases, 'test_cases') else 0
                    
                    self.logger.info(f"[Kimi] Generated {test_count} test cases for {endpoint_id}")
                    
                    if test_count >= 5:
                        # Sufficient test cases generated
                        self.logger.info(f"[Kimi] Success - sufficient test cases for {endpoint_id}")
                        return result.test_cases, result.token_usage
                    elif retry < max_retries:
                        # Not enough test cases, log warning and retry
                        self.logger.warning(
                            f"[Kimi] Only {test_count} test cases for {endpoint_id}, "
                            f"minimum 5 required. Retrying ({retry + 1}/{max_retries})..."
                        )
                        # Add a small delay before retry
                        await asyncio.sleep(2)
                    else:
                        # Final attempt still insufficient, log error but return what we have
                        self.logger.error(
                            f"[Kimi] Only {test_count} test cases for {endpoint_id} "
                            f"after {max_retries} retries. Minimum 5 required. Proceeding with partial results."
                        )
                        return result.test_cases, result.token_usage
                        
                except Exception as e:
                    self.logger.error(f"[Kimi] Error during attempt {retry + 1} for {endpoint_id}: {e}")
                    if retry >= max_retries:
                        raise
                    await asyncio.sleep(2)
            
            # Should not reach here
            raise ProviderGenerationError(f"Failed to generate test cases after {max_retries + 1} attempts")
        
        # Apply timeout protection (50 seconds total for all retries)
        try:
            self.logger.info(f"[Kimi] Applying 50s timeout for generation")
            return await asyncio.wait_for(_generate_with_retries(), timeout=50.0)
        except asyncio.TimeoutError:
            endpoint_id = endpoint.get_endpoint_id()
            self.logger.error(f"[Kimi] Generation timeout after 60s for {endpoint_id}")
            raise ProviderGenerationError(f"Generation timeout after 60s for {endpoint_id}")
    
    def get_max_workers(self) -> int:
        """Get maximum concurrent workers.
        
        Returns:
            Maximum number of concurrent workers
        """
        # Read from environment variable with default fallback
        max_workers = int(os.getenv("CASECRAFT_KIMI_MAX_WORKERS", "2"))
        return min(self.config.workers, max_workers)
    
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
        
        # Log the model being used (no validation - let API handle it)
        self.logger.info(f"Using Kimi model: {self.config.model}")
        
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