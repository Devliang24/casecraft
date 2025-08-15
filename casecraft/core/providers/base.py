"""Base class for LLM providers."""

import time
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Callable
from pathlib import Path
import logging

from casecraft.models.api_spec import APIEndpoint
from casecraft.models.test_case import TestCaseCollection
from casecraft.models.usage import TokenUsage
from casecraft.core.providers.exceptions import (
    ProviderError, ProviderEmptyResponseError, ProviderInvalidFormatError,
    ProviderTimeoutError, ProviderAuthError, ProviderQuotaError, ProviderRateLimitError
)


class LLMResponse:
    """Response from LLM provider."""
    
    def __init__(
        self, 
        content: str,
        provider: str,
        model: str,
        token_usage: Optional[TokenUsage] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Initialize LLM response.
        
        Args:
            content: Response content
            provider: Provider name
            model: Model name
            token_usage: Token usage information
            metadata: Additional metadata
        """
        self.content = content
        self.provider = provider
        self.model = model
        self.token_usage = token_usage
        self.metadata = metadata or {}


class ProviderConfig:
    """Configuration for a provider."""
    
    def __init__(
        self,
        name: str,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 3,
        temperature: float = 0.7,
        stream: bool = True,
        workers: int = 1,
        use_structured_output: bool = True,
        **kwargs
    ):
        """Initialize provider configuration.
        
        Args:
            name: Provider name
            model: Model name
            api_key: API key
            base_url: Base URL for API
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries
            temperature: Temperature for generation
            stream: Whether to stream responses
            workers: Maximum concurrent workers
            use_structured_output: Use structured output format for JSON responses
            **kwargs: Additional provider-specific options
        """
        self.name = name
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.temperature = temperature
        self.stream = stream
        self.workers = workers
        self.use_structured_output = use_structured_output
        self.extra = kwargs


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, config: ProviderConfig):
        """Initialize LLM provider.
        
        Args:
            config: Provider configuration
        """
        self.config = config
        self.logger = logging.getLogger(f"provider.{self.name}")
    
    def create_friendly_error(self, error: Exception, request_data: Optional[Dict[str, Any]] = None) -> ProviderError:
        """Convert any error to a user-friendly ProviderError.
        
        Args:
            error: Original error
            request_data: Request data for debugging
            
        Returns:
            ProviderError with friendly message
        """
        if isinstance(error, ProviderError):
            # Already a friendly error, just save debug info if needed
            if request_data and not error.debug_file:
                error.save_debug_info(request_data)
            return error
        
        # Convert common errors to friendly errors
        error_str = str(error).lower()
        
        if "timeout" in error_str or "timed out" in error_str:
            return ProviderTimeoutError(self.name, self.config.timeout)
        elif "401" in error_str or "unauthorized" in error_str or "invalid api key" in error_str:
            return ProviderAuthError(self.name)
        elif "429" in error_str or "rate limit" in error_str:
            return ProviderRateLimitError(self.name)
        elif "quota" in error_str or "billing" in error_str:
            return ProviderQuotaError(self.name)
        elif "expecting value" in error_str and "char 0" in error_str:
            return ProviderEmptyResponseError(self.name)
        elif "json" in error_str and ("decode" in error_str or "parse" in error_str):
            return ProviderInvalidFormatError(self.name, "JSON", "Invalid format", str(error))
        else:
            # Generic provider error
            provider_error = ProviderError(
                message=str(error),
                provider_name=self.name,
                suggestions=[
                    "Check network connection",
                    f"Verify {self.name} API configuration",
                    "Retry later",
                    "Check detailed logs for more information"
                ]
            )
            if request_data:
                provider_error.save_debug_info(request_data)
            return provider_error
    
    def save_debug_response(self, content: Any, error_type: str, request_data: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Save debug response to file.
        
        Args:
            content: Response content
            error_type: Type of error
            request_data: Request data
            
        Returns:
            Path to debug file or None if failed
        """
        try:
            debug_dir = Path("debug_responses")
            debug_dir.mkdir(exist_ok=True)
            
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{self.name}_{error_type}_{timestamp_str}.json"
            filepath = debug_dir / filename
            
            debug_data = {
                "debug_info": {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "provider": self.name,
                    "error_type": error_type
                },
                "response": {
                    "content": str(content) if content is not None else None,
                    "content_type": type(content).__name__,
                    "content_length": len(str(content)) if content is not None else 0
                }
            }
            
            if request_data:
                debug_data["request"] = request_data
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(debug_data, f, ensure_ascii=False, indent=2)
            
            return str(filepath)
        except Exception as e:
            self.logger.warning(f"Failed to save debug response: {e}")
            return None
    
    def calculate_provider_progress(self, 
                                  base_progress: float, 
                                  content_length: int = 0,
                                  has_finish_reason: bool = False,
                                  is_streaming: bool = False,
                                  retry_count: int = 0) -> float:
        """Calculate provider-level progress that never reaches 100%.
        
        This method ensures consistent progress calculation across all providers.
        The provider layer should never reach 100% since it doesn't know if
        subsequent validation (format parsing, test case generation) will succeed.
        
        Args:
            base_progress: Current progress from streaming/waiting (0.0-1.0)
            content_length: Length of response content in characters
            has_finish_reason: Whether the response has a proper finish reason
            is_streaming: Whether this is streaming mode
            retry_count: Number of retries attempted (affects max progress)
            
        Returns:
            Final progress value (0.0-0.98), never 100%
        """
        # Apply retry penalty - each retry reduces max achievable progress
        retry_penalty = min(retry_count * 0.05, 0.15)  # Max 15% penalty for 3+ retries
        
        # Set maximum progress based on mode
        if is_streaming:
            # Streaming mode: higher ceiling since we get real-time progress
            max_progress = 0.92 - retry_penalty
        else:
            # Non-streaming mode: slightly lower ceiling
            max_progress = 0.90 - retry_penalty
        
        # Content length bonus (up to +3%)
        if content_length > 0:
            # Bonus based on content length: more content = more processing done
            # 1000 chars = ~1%, 5000+ chars = full 3% bonus
            content_bonus = min(content_length / 5000, 1.0) * 0.03
            max_progress += content_bonus
        
        # Finish reason bonus (+2%)
        if has_finish_reason:
            max_progress += 0.02
        
        # Ensure we never exceed 98% and respect base progress
        final_progress = min(base_progress, max_progress, 0.98)
        
        # Never go backwards
        final_progress = max(final_progress, base_progress * 0.95)
        
        return final_progress
    
    def calculate_retry_rollback_progress(self, current_progress: float, attempt: int) -> float:
        """Calculate progress rollback for retry scenarios.
        
        Args:
            current_progress: Current progress value
            attempt: Retry attempt number (1-based)
            
        Returns:
            Rolled back progress value
        """
        # Progressive rollback: more attempts = more rollback
        # Attempt 1: 20% rollback, Attempt 2: 30% rollback, Attempt 3+: 40% rollback
        rollback_percentage = min(0.20 + (attempt - 1) * 0.10, 0.40)
        rollback_amount = current_progress * rollback_percentage
        
        # Ensure minimum progress of 10%
        rolled_back = max(current_progress - rollback_amount, 0.10)
        
        return rolled_back
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Get provider name.
        
        Returns:
            Provider name
        """
        pass
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate response from prompt.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt
            progress_callback: Callback for progress updates
            **kwargs: Additional generation parameters
            
        Returns:
            LLM response
        """
        pass
    
    @abstractmethod
    async def generate_test_cases(
        self,
        endpoint: APIEndpoint,
        progress_callback: Optional[Callable[[float], None]] = None,
        **kwargs
    ) -> tuple[TestCaseCollection, Optional[TokenUsage]]:
        """Generate test cases for an API endpoint.
        
        Args:
            endpoint: API endpoint
            progress_callback: Callback for progress updates
            **kwargs: Additional generation parameters
            
        Returns:
            Tuple of (test cases, token usage)
        """
        pass
    
    @abstractmethod
    def get_max_workers(self) -> int:
        """Get maximum concurrent workers for this provider.
        
        Returns:
            Maximum number of concurrent workers
        """
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """Validate provider configuration.
        
        Returns:
            True if configuration is valid
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check provider health.
        
        Returns:
            True if provider is healthy
        """
        pass
    
    async def close(self) -> None:
        """Clean up provider resources."""
        pass