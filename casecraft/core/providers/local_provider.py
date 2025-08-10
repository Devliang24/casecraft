"""Local Provider implementation for Ollama and vLLM."""

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


class LocalProvider(LLMProvider):
    """本地部署模型提供商 (Ollama/vLLM)."""
    
    name = "local"
    
    def __init__(self, config: ProviderConfig):
        """Initialize Local provider.
        
        Args:
            config: Provider configuration
        """
        super().__init__(config)
        
        # Determine local server type from config
        self.server_type = config.extra.get("server_type", "ollama") if hasattr(config, "extra") else "ollama"
        
        # Set default base URL based on server type
        if self.server_type == "ollama":
            self.base_url = config.base_url or "http://localhost:11434"
        elif self.server_type == "vllm":
            self.base_url = config.base_url or "http://localhost:8000"
        else:
            # Generic OpenAI-compatible local server
            self.base_url = config.base_url or "http://localhost:8000"
        
        self.logger = get_logger(f"provider.{self.name}")
        
        # Local deployments can handle more concurrent requests
        self._semaphore = asyncio.Semaphore(config.workers)
        
        # Different headers based on server type
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=config.timeout,
            headers=headers
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
        """Generate response from local model.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt
            progress_callback: Progress callback function
            **kwargs: Additional generation parameters
            
        Returns:
            LLM response
        """
        async with self._semaphore:
            if self.server_type == "ollama":
                return await self._generate_ollama(prompt, system_prompt, progress_callback, **kwargs)
            else:
                # vLLM and other OpenAI-compatible servers
                return await self._generate_openai_compatible(prompt, system_prompt, progress_callback, **kwargs)
    
    async def _generate_ollama(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate response using Ollama API.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt
            progress_callback: Progress callback function
            **kwargs: Additional generation parameters
            
        Returns:
            LLM response
        """
        # Combine system and user prompts for Ollama
        full_prompt = ""
        if system_prompt:
            full_prompt = f"System: {system_prompt}\n\nUser: {prompt}"
        else:
            full_prompt = prompt
        
        # Ollama API payload
        payload = {
            "model": self.config.model,  # e.g., "llama2", "mistral", "codellama"
            "prompt": full_prompt,
            "stream": self.config.stream,
            "options": {
                "temperature": kwargs.get("temperature", self.config.temperature),
                "top_p": kwargs.get("top_p", 0.9),
                "num_predict": kwargs.get("max_tokens", 2000)
            }
        }
        
        self.logger.debug(f"Ollama request - Model: {self.config.model}")
        
        try:
            if self.config.stream and progress_callback:
                return await self._generate_ollama_stream(payload, progress_callback)
            else:
                return await self._generate_ollama_non_stream(payload, progress_callback)
                
        except Exception as e:
            self.logger.error(f"Ollama generation failed: {str(e)}")
            raise ProviderGenerationError(f"Ollama API error: {e}") from e
    
    async def _generate_ollama_non_stream(
        self,
        payload: Dict[str, Any],
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> LLMResponse:
        """Generate Ollama response without streaming."""
        # Update progress
        if progress_callback:
            progress_callback(0.1)
        
        # Make request
        response = await self.client.post("/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()
        
        # Update progress
        if progress_callback:
            progress_callback(0.9)
        
        # Parse response
        content = data.get("response", "")
        
        # Ollama provides basic token info
        token_usage = None
        if "eval_count" in data or "prompt_eval_count" in data:
            token_usage = TokenUsage(
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                model=self.config.model
            )
        
        if progress_callback:
            progress_callback(1.0)
        
        return LLMResponse(
            content=content,
            provider=self.name,
            model=self.config.model,
            token_usage=token_usage,
            metadata={
                "done": data.get("done"),
                "context": data.get("context"),
                "total_duration": data.get("total_duration"),
                "eval_duration": data.get("eval_duration")
            }
        )
    
    async def _generate_ollama_stream(
        self,
        payload: Dict[str, Any],
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> LLMResponse:
        """Generate Ollama response with streaming."""
        content_chunks = []
        token_usage = None
        metadata = {}
        
        try:
            async with self.client.stream("POST", "/api/generate", json=payload) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        
                        # Extract content
                        if "response" in data:
                            content_chunks.append(data["response"])
                            
                            # Update progress
                            if progress_callback:
                                progress = 0.2 + min(len(content_chunks) / 100, 0.7)
                                progress_callback(progress)
                        
                        # Check if done
                        if data.get("done"):
                            # Get final token counts
                            if "eval_count" in data or "prompt_eval_count" in data:
                                token_usage = TokenUsage(
                                    prompt_tokens=data.get("prompt_eval_count", 0),
                                    completion_tokens=data.get("eval_count", 0),
                                    total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
                                    model=self.config.model
                                )
                            
                            metadata = {
                                "context": data.get("context"),
                                "total_duration": data.get("total_duration"),
                                "eval_duration": data.get("eval_duration")
                            }
                            break
                            
                    except json.JSONDecodeError:
                        self.logger.warning(f"Failed to parse stream data: {line}")
                        continue
                
                if progress_callback:
                    progress_callback(1.0)
                
                return LLMResponse(
                    content="".join(content_chunks),
                    provider=self.name,
                    model=self.config.model,
                    token_usage=token_usage,
                    metadata=metadata
                )
                
        except Exception as e:
            self.logger.error(f"Streaming generation failed: {e}")
            raise ProviderGenerationError(f"Streaming failed: {e}") from e
    
    async def _generate_openai_compatible(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate response using OpenAI-compatible API (vLLM, etc).
        
        Args:
            prompt: User prompt
            system_prompt: System prompt
            progress_callback: Progress callback function
            **kwargs: Additional generation parameters
            
        Returns:
            LLM response
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        # OpenAI-compatible payload
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
            "top_p": kwargs.get("top_p", 1.0),
            "max_tokens": kwargs.get("max_tokens", 2000),
            "stream": self.config.stream
        }
        
        self.logger.debug(f"OpenAI-compatible request - Model: {self.config.model}")
        
        try:
            if self.config.stream and progress_callback:
                return await self._generate_openai_stream(payload, progress_callback)
            else:
                return await self._generate_openai_non_stream(payload, progress_callback)
                
        except Exception as e:
            self.logger.error(f"Local generation failed: {str(e)}")
            raise ProviderGenerationError(f"Local API error: {e}") from e
    
    async def _generate_openai_non_stream(
        self,
        payload: Dict[str, Any],
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> LLMResponse:
        """Generate OpenAI-compatible response without streaming."""
        # Update progress
        if progress_callback:
            progress_callback(0.1)
        
        # Determine endpoint based on server type
        endpoint = "/v1/chat/completions" if self.server_type == "vllm" else "/chat/completions"
        
        # Make request
        response = await self.client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
        
        # Update progress
        if progress_callback:
            progress_callback(0.9)
        
        # Parse OpenAI-format response
        choice = data["choices"][0]
        usage = data.get("usage", {})
        
        # Create token usage
        token_usage = None
        if usage:
            token_usage = TokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                model=self.config.model
            )
        
        if progress_callback:
            progress_callback(1.0)
        
        return LLMResponse(
            content=choice["message"]["content"],
            provider=self.name,
            model=self.config.model,
            token_usage=token_usage,
            metadata={
                "finish_reason": choice.get("finish_reason"),
                "id": data.get("id")
            }
        )
    
    async def _generate_openai_stream(
        self,
        payload: Dict[str, Any],
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> LLMResponse:
        """Generate OpenAI-compatible response with streaming."""
        content_chunks = []
        token_usage = None
        finish_reason = None
        
        # Determine endpoint
        endpoint = "/v1/chat/completions" if self.server_type == "vllm" else "/chat/completions"
        
        try:
            async with self.client.stream("POST", endpoint, json=payload) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if not line or line.startswith(":"):
                        continue
                    
                    if line.startswith("data: "):
                        data_str = line[6:]
                        
                        if data_str == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            
                            if "choices" in data and data["choices"]:
                                choice = data["choices"][0]
                                delta = choice.get("delta", {})
                                
                                if "content" in delta:
                                    content_chunks.append(delta["content"])
                                    
                                    if progress_callback:
                                        progress = 0.2 + min(len(content_chunks) / 100, 0.7)
                                        progress_callback(progress)
                                
                                if choice.get("finish_reason"):
                                    finish_reason = choice["finish_reason"]
                                    
                        except json.JSONDecodeError:
                            self.logger.warning(f"Failed to parse SSE data: {data_str}")
                            continue
                
                if progress_callback:
                    progress_callback(1.0)
                
                # Estimate tokens for local models
                content = "".join(content_chunks)
                estimated_tokens = len(content) // 4
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
                    metadata={"finish_reason": finish_reason}
                )
                
        except Exception as e:
            self.logger.error(f"Streaming generation failed: {e}")
            raise ProviderGenerationError(f"Streaming failed: {e}") from e
    
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
            
            # Create a custom LLM client
            class LocalLLMClient(LLMClient):
                def __init__(self, config, provider):
                    super().__init__(config)
                    self.provider = provider
                
                async def generate(self, prompt, system_prompt=None, progress_callback=None, **kwargs):
                    response = await self.provider.generate(
                        prompt, system_prompt, progress_callback, **kwargs
                    )
                    from casecraft.core.generation.llm_client import LLMResponse as ClientResponse
                    return ClientResponse(
                        content=response.content,
                        model=response.model,
                        usage=response.token_usage.__dict__ if response.token_usage else None,
                        finish_reason=response.metadata.get("finish_reason"),
                        retry_count=0
                    )
            
            llm_client = LocalLLMClient(llm_config, self)
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
            Maximum number of concurrent workers (configurable for local)
        """
        return self.config.workers  # Fully configurable for local deployments
    
    def validate_config(self) -> bool:
        """Validate provider configuration.
        
        Returns:
            True if configuration is valid
        """
        if not self.config.model:
            self.logger.error("Model name is required for Local provider")
            return False
        
        # API key is optional for local deployments
        
        # Validate server type
        valid_server_types = ["ollama", "vllm", "openai"]
        if hasattr(self.config, "extra") and self.config.extra.get("server_type"):
            server_type = self.config.extra.get("server_type")
            if server_type not in valid_server_types:
                self.logger.warning(f"Unknown server type: {server_type}. Valid types: {valid_server_types}")
        
        return True
    
    async def health_check(self) -> bool:
        """Check provider health.
        
        Returns:
            True if provider is healthy
        """
        try:
            # Check server availability
            if self.server_type == "ollama":
                # Check Ollama API
                response = await self.client.get("/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
                
                # Check if our model is available
                model_names = [m.get("name") for m in models]
                if self.config.model not in model_names:
                    self.logger.warning(f"Model {self.config.model} not found in Ollama. Available: {model_names}")
                
                return True
            else:
                # Try a simple generation for OpenAI-compatible servers
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
        self.logger.debug("Local provider closed")