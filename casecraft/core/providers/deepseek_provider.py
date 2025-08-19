"""DeepSeek Provider implementation."""

import asyncio
import json
import os
from typing import Any, Dict, Optional, Callable
import httpx

from casecraft.core.providers.base import LLMProvider, LLMResponse
from casecraft.models.provider_config import ProviderConfig
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
from casecraft.utils.constants import HTTP_RATE_LIMIT, PROVIDER_BASE_URLS, PROVIDER_MAX_WORKERS, PROVIDER_MODELS


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
            # Use default from constants
            self.base_url = PROVIDER_BASE_URLS.get('deepseek')
            self.logger.info(f"Using default base URL: {self.base_url}")
        self.logger = get_logger(f"provider.{self.name}")
        
        # Configure concurrent requests from constants
        max_workers = PROVIDER_MAX_WORKERS.get('deepseek', 3)
        # Allow environment override
        env_workers = os.getenv("CASECRAFT_DEEPSEEK_MAX_WORKERS")
        if env_workers:
            max_workers = int(env_workers)
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
            payload = {
                "model": self.config.model,  # e.g., "deepseek-chat", "deepseek-coder"
                "messages": messages,
                "temperature": kwargs.get("temperature", self.config.temperature),
                "top_p": kwargs.get("top_p", float(os.getenv("CASECRAFT_DEFAULT_TOP_P", "0.9"))),
                "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
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
                # Convert to friendly error
                friendly_error = self.create_friendly_error(e, {
                    "model": self.config.model,
                    "stream": self.config.stream,
                    "messages": payload.get("messages", [])
                })
                self.logger.error(f"DeepSeek generation failed: {friendly_error.get_friendly_message()}")
                raise friendly_error from e
    
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
        
        if response.status_code == HTTP_RATE_LIMIT:
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
            # Convert to friendly error  
            friendly_error = self.create_friendly_error(Exception(error_msg))
            raise friendly_error
        
        if progress_callback:
            progress_callback(0.9)  # Processing response
        
        data = response.json()
        
        # Extract response
        choice = data["choices"][0]
        content = choice["message"]["content"]
        finish_reason = choice.get("finish_reason")
        
        # Extract token usage
        usage = data.get("usage", {})
        token_usage = TokenUsage(
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0)
        )
        
        # Calculate final provider progress based on actual response
        if progress_callback:
            final_progress = self.calculate_provider_progress(
                base_progress=0.9,  # Base from processing phase
                content_length=len(content) if content else 0,
                has_finish_reason=bool(finish_reason),
                is_streaming=False
            )
            progress_callback(final_progress)
        
        return LLMResponse(
            content=content,
            provider=self.name,
            model=self.config.model,
            token_usage=token_usage,
            metadata={"raw_response": data}
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
            if response.status_code == HTTP_RATE_LIMIT:
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
                # Convert to friendly error
                friendly_error = self.create_friendly_error(Exception(error_msg))
                raise friendly_error
            
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
                        if "choices" in chunk and chunk["choices"] and chunk["choices"][0]:
                            choice = chunk["choices"][0]
                            delta = choice.get("delta", {}) if choice else {}
                            
                            if "content" in delta:
                                content_chunks.append(delta["content"])
                            
                            # Track finish reason
                            if choice and "finish_reason" in choice:
                                finish_reason = choice["finish_reason"]
                        
                        # Extract usage information (usually in the last chunk)
                        if "usage" in chunk and chunk["usage"]:
                            usage = chunk["usage"]
                            token_usage = TokenUsage(
                                prompt_tokens=usage.get("prompt_tokens", 0) if usage else 0,
                                completion_tokens=usage.get("completion_tokens", 0) if usage else 0,
                                total_tokens=usage.get("total_tokens", 0) if usage else 0
                            )
                        
                        # Update progress
                        if progress_callback:
                            chunks_received += 1
                            progress = min(0.95, chunks_received / total_estimated_chunks)
                            progress_callback(progress)
                            
                    except json.JSONDecodeError as e:
                        self.logger.warning(f"Failed to parse streaming chunk: {e}")
                        continue
                    except Exception as e:
                        self.logger.error(f"Error processing streaming chunk: {e}")
                        self.logger.debug(f"Chunk data: {line_data}")
                        continue
        
        # Combine content first
        content = "".join(content_chunks)
        
        # Calculate final provider progress based on actual response
        if progress_callback:
            # Use the last dynamic progress or base streaming progress
            base_streaming_progress = min(0.95, chunks_received / max(total_estimated_chunks, 1))
            final_progress = self.calculate_provider_progress(
                base_progress=base_streaming_progress,
                content_length=len(content) if content else 0,
                has_finish_reason=bool(finish_reason),
                is_streaming=True
            )
            progress_callback(final_progress)
        
        # If no usage info was provided, estimate it
        if not token_usage:
            # Rough estimation based on content length
            # Extract prompt from payload for estimation
            prompt_text = ""
            if "messages" in payload:
                prompt_text = " ".join(msg.get("content", "") for msg in payload["messages"] if msg and isinstance(msg, dict))
            
            token_usage = TokenUsage(
                prompt_tokens=len(prompt_text) // 4,  # Rough estimate
                completion_tokens=len(content) // 4,
                total_tokens=(len(prompt_text) + len(content)) // 4
            )
        
        return LLMResponse(
            content=content,
            provider=self.name,
            model=self.config.model,
            token_usage=token_usage,
            metadata={"finish_reason": finish_reason}
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
        
        # Validate model name using constants
        valid_models = PROVIDER_MODELS.get('deepseek', [])
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