"""DeepSeek Provider implementation."""

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


class DeepSeekProvider(LLMProvider):
    """DeepSeek AI Provider implementation."""
    
    name = "deepseek"
    
    def __init__(self, config: ProviderConfig):
        """Initialize DeepSeek provider.
        
        Args:
            config: Provider configuration
        """
        super().__init__(config)
        # DeepSeek API endpoint - use configured or default
        self.base_url = config.base_url
        if not self.base_url:
            # Use default if not configured
            self.base_url = "https://api.deepseek.com/v1"
            self.logger.info(f"Using default base URL: {self.base_url}")
        self.logger = get_logger(f"provider.{self.name}")
        
        # Configure concurrent requests from environment
        max_workers = int(os.getenv("CASECRAFT_DEEPSEEK_MAX_WORKERS", "3"))
        self._semaphore = asyncio.Semaphore(min(config.workers, max_workers))
        
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
        """Generate response from DeepSeek.
        
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
            
            # DeepSeek API payload format (OpenAI compatible)
            default_max_tokens = int(os.getenv("CASECRAFT_DEFAULT_MAX_TOKENS", "8192"))
            max_tokens = kwargs.get("max_tokens", default_max_tokens)
            
            payload = {
                "model": self.config.model,  # e.g., "deepseek-chat", "deepseek-coder"
                "messages": messages,
                "temperature": kwargs.get("temperature", self.config.temperature),
                "top_p": kwargs.get("top_p", float(os.getenv("CASECRAFT_DEFAULT_TOP_P", "0.9"))),
                "max_tokens": max_tokens,
                "stream": self.config.stream
            }
            
            # Add stream_options to get token usage in streaming mode
            if self.config.stream:
                payload["stream_options"] = {"include_usage": True}
            
            # Add structured output format if enabled
            # DeepSeek supports structured output
            if self.config.use_structured_output:
                payload["response_format"] = {"type": "json_object"}
            
            self.logger.debug(f"DeepSeek request - Model: {self.config.model}, Messages: {len(messages)}")
            
            try:
                if self.config.stream and progress_callback:
                    return await self._generate_stream(payload, progress_callback)
                else:
                    return await self._generate_non_stream(payload, progress_callback)
                    
            except Exception as e:
                self.logger.error(f"DeepSeek generation failed: {str(e)}")
                raise ProviderGenerationError(f"DeepSeek API error: {e}") from e
    
    async def _generate_non_stream(
        self, 
        payload: Dict[str, Any],
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> LLMResponse:
        """Generate response without streaming."""
        # Simulate progress for non-streaming mode
        if progress_callback:
            progress_callback(0.1)  # Starting
        
        response = await self.client.post(
            "/chat/completions",
            json=payload
        )
        
        if progress_callback:
            progress_callback(0.8)  # Near completion
        
        if response.status_code == 429:
            raise ProviderRateLimitError("DeepSeek API rate limit exceeded")
        
        if response.status_code != 200:
            error_msg = f"DeepSeek API error: {response.status_code}"
            try:
                error_data = response.json()
                if "error" in error_data:
                    if isinstance(error_data['error'], dict):
                        error_msg = f"DeepSeek API error: {error_data['error'].get('message', error_data['error'])}"
                    else:
                        error_msg = f"DeepSeek API error: {error_data.get('error', 'Unknown error')}"
            except:
                pass
            raise ProviderGenerationError(error_msg)
        
        if progress_callback:
            progress_callback(0.9)  # Processing response
        
        data = response.json()
        
        # Extract response
        content = data["choices"][0]["message"]["content"]
        
        # Extract token usage
        usage = data.get("usage", {})
        token_usage = TokenUsage(
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0)
        )
        
        if progress_callback:
            progress_callback(1.0)  # Complete
        
        return LLMResponse(
            content=content,
            model=self.config.model,
            usage=token_usage,
            raw_response=data
        )
    
    async def _generate_stream(
        self,
        payload: Dict[str, Any],
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> LLMResponse:
        """Generate response with streaming."""
        content_chunks = []
        token_usage = None
        finish_reason = None
        
        # Track progress
        total_estimated_chunks = 50  # Estimate for progress calculation
        chunks_received = 0
        
        async with self.client.stream(
            "POST",
            "/chat/completions",
            json=payload
        ) as response:
            if response.status_code == 429:
                raise ProviderRateLimitError("DeepSeek API rate limit exceeded")
            
            if response.status_code != 200:
                error_text = await response.aread()
                error_msg = f"DeepSeek API error: {response.status_code}"
                try:
                    error_data = json.loads(error_text)
                    if "error" in error_data:
                        if isinstance(error_data['error'], dict):
                            error_msg = f"DeepSeek API error: {error_data['error'].get('message', error_data['error'])}"
                        else:
                            error_msg = f"DeepSeek API error: {error_data.get('error', 'Unknown error')}"
                except:
                    pass
                raise ProviderGenerationError(error_msg)
            
            async for line in response.aiter_lines():
                if not line:
                    continue
                    
                if line.startswith("data: "):
                    line_data = line[6:]  # Remove "data: " prefix
                    
                    if line_data == "[DONE]":
                        break
                    
                    try:
                        chunk = json.loads(line_data)
                        
                        # Extract content delta
                        if "choices" in chunk and chunk["choices"]:
                            delta = chunk["choices"][0].get("delta", {})
                            
                            if "content" in delta:
                                content_chunks.append(delta["content"])
                            
                            # Track finish reason
                            if "finish_reason" in chunk["choices"][0]:
                                finish_reason = chunk["choices"][0]["finish_reason"]
                        
                        # Extract usage information (usually in the last chunk)
                        if "usage" in chunk:
                            usage = chunk["usage"]
                            token_usage = TokenUsage(
                                input_tokens=usage.get("prompt_tokens", 0),
                                output_tokens=usage.get("completion_tokens", 0),
                                total_tokens=usage.get("total_tokens", 0)
                            )
                        
                        # Update progress
                        if progress_callback:
                            chunks_received += 1
                            progress = min(0.95, chunks_received / total_estimated_chunks)
                            progress_callback(progress)
                            
                    except json.JSONDecodeError as e:
                        self.logger.warning(f"Failed to parse streaming chunk: {e}")
                        continue
        
        # Final progress
        if progress_callback:
            progress_callback(1.0)
        
        # Combine content
        content = "".join(content_chunks)
        
        # If no usage info was provided, estimate it
        if not token_usage:
            # Rough estimation based on content length
            token_usage = TokenUsage(
                input_tokens=len(prompt) // 4,  # Rough estimate
                output_tokens=len(content) // 4,
                total_tokens=(len(prompt) + len(content)) // 4
            )
        
        return LLMResponse(
            content=content,
            model=self.config.model,
            usage=token_usage,
            raw_response={"finish_reason": finish_reason}
        )
    
    async def generate_test_cases(
        self,
        endpoint: APIEndpoint,
        api_version: Optional[str] = None
    ) -> TestCaseCollection:
        """Generate test cases for an API endpoint.
        
        Args:
            endpoint: API endpoint to generate test cases for
            api_version: API version
            
        Returns:
            Collection of test cases
        """
        # Lazy initialize test generator
        if not self._test_generator:
            # Create a simple LLM client wrapper for the generator
            from casecraft.core.generation.llm_client import LLMClient
            llm_client = LLMClient(provider=self)
            self._test_generator = TestCaseGenerator(llm_client, api_version)
        
        return await self._test_generator.generate(endpoint)
    
    def get_max_workers(self) -> int:
        """Get maximum number of concurrent workers.
        
        Returns:
            Maximum workers count
        """
        # Read from environment variable with default fallback
        max_workers = int(os.getenv("CASECRAFT_DEEPSEEK_MAX_WORKERS", "3"))
        return min(self.config.workers, max_workers)
    
    def validate_config(self) -> bool:
        """Validate provider configuration.
        
        Returns:
            True if configuration is valid
        """
        if not self.config.api_key:
            self.logger.error("DeepSeek API key is not configured")
            return False
        
        if not self.config.model:
            self.logger.error("DeepSeek model is not configured")
            return False
        
        # Validate model name
        valid_models = ["deepseek-chat", "deepseek-coder", "deepseek-v2", "deepseek-v2.5"]
        if self.config.model not in valid_models:
            self.logger.warning(
                f"Model '{self.config.model}' may not be valid. "
                f"Known models: {', '.join(valid_models)}"
            )
        
        return True
    
    async def health_check(self) -> bool:
        """Perform health check on the provider.
        
        Returns:
            True if provider is healthy
        """
        try:
            # Make a simple API call to verify connectivity
            response = await self.client.get("/models")
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close the provider and cleanup resources."""
        if self.client:
            await self.client.aclose()
            self.logger.debug("DeepSeek client closed")