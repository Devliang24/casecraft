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
from casecraft.models.provider_config import ProviderConfig
from casecraft.core.providers.exceptions import (
    ProviderError, ProviderEmptyResponseError, ProviderInvalidFormatError,
    ProviderTimeoutError, ProviderAuthError, ProviderQuotaError, ProviderRateLimitError
)
from casecraft.utils.constants import HTTP_RATE_LIMIT


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




class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, config: ProviderConfig):
        """Initialize LLM provider.
        
        Args:
            config: Provider configuration
        """
        self.config = config
        self.logger = logging.getLogger(f"provider.{self.name}")
    
    def create_friendly_error(self, error: Exception, request_data: Optional[Dict[str, Any]] = None, retry_stats: Optional[Dict[str, Any]] = None) -> ProviderError:
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
        elif str(HTTP_RATE_LIMIT) in error_str or "rate limit" in error_str:
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
                retry_stats=retry_stats,
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
    
    def log_retry_attempt(self, attempt: int, max_retries: int, endpoint: str, reason: str = "error") -> None:
        """Log a retry attempt with unified format.
        
        Args:
            attempt: Current attempt number (0-based)
            max_retries: Maximum number of retries allowed
            endpoint: API endpoint being retried
            reason: Reason for retry
        """
        if attempt > 0:
            self.logger.info(f"[{self.name.upper()}] 🔄 Retry {attempt + 1}/{max_retries + 1} - {reason} - {endpoint}")
        else:
            self.logger.info(f"[{self.name.upper()}] Initial request to {endpoint}")
    
    def log_retry_wait(self, attempt: int, max_retries: int, wait_time: float, reason: str) -> None:
        """Log retry wait with unified format.
        
        Args:
            attempt: Current attempt number (0-based)  
            max_retries: Maximum number of retries allowed
            wait_time: Wait time in seconds
            reason: Reason for retry
        """
        self.logger.info(f"[Retry {attempt + 1}/{max_retries + 1}] {reason}, waiting {wait_time:.2f}s...")
    
    def log_retry_success(self, attempt: int, total_time: float) -> None:
        """Log successful request after retries.
        
        Args:
            attempt: Final attempt number (0-based)
            total_time: Total time taken including retries
        """
        if attempt > 0:
            self.logger.info(f"[{self.name.upper()}] ✅ Request succeeded after {attempt + 1} attempts ({attempt} retries, {total_time:.1f}s total)")
    
    def log_retry_failure(self, max_retries: int, total_time: float, last_error: Exception) -> None:
        """Log final failure after all retries exhausted.
        
        Args:
            max_retries: Maximum number of retries that were attempted
            total_time: Total time spent on all attempts
            last_error: The final error that caused failure
        """
        attempts = max_retries + 1
        self.logger.error(
            f"[{self.name.upper()}] ❌ All retries exhausted after {attempts} attempts "
            f"in {total_time:.1f}s. Last error: {last_error}"
        )
        self.logger.info(
            f"[{self.name.upper()}] Retry summary: {attempts} attempts, "
            f"{total_time:.1f}s total time, "
            f"avg {total_time/attempts:.1f}s per attempt"
        )
    
    def safe_progress_callback(self, progress_callback: Optional[Callable], progress: float, retry_info: Optional[Dict[str, Any]] = None) -> None:
        """Safely call progress callback with error handling and rate limiting.
        
        Args:
            progress_callback: Progress callback function
            progress: Progress value (0.0-1.0)
            retry_info: Optional retry information
        """
        if not progress_callback:
            return
        
        try:
            # Rate limiting: Store last update time and avoid too frequent updates
            current_time = time.time()
            last_update_key = f"_last_progress_update_{id(progress_callback)}"
            
            if hasattr(self, last_update_key):
                last_update = getattr(self, last_update_key)
                if current_time - last_update < 0.1:  # Minimum 100ms between updates
                    return
            
            setattr(self, last_update_key, current_time)
            
            # Execute callback with timeout protection
            progress_callback(progress, retry_info)
            
        except Exception as e:
            # Log but don't fail on progress callback errors
            self.logger.debug(f"Progress callback error: {e}")
    
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