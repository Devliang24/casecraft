"""Exceptions for provider system."""

import time
import json
from typing import List, Optional, Any, Dict
from pathlib import Path


class ProviderError(Exception):
    """Base exception for provider-related errors with enhanced error reporting."""
    
    def __init__(self, 
                 message: str,
                 provider_name: Optional[str] = None,
                 raw_response: Optional[str] = None,
                 suggestions: Optional[List[str]] = None,
                 debug_file: Optional[str] = None,
                 error_code: Optional[str] = None,
                 retry_stats: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.provider_name = provider_name
        self.raw_response = raw_response
        self.suggestions = suggestions or []
        self.debug_file = debug_file
        self.error_code = error_code
        self.retry_stats = retry_stats or {}
        self.timestamp = time.time()
    
    def get_friendly_message(self) -> str:
        """Return user-friendly error message."""
        if not self.provider_name:
            return str(self)
        
        lines = []
        lines.append(f"⚠️  {self.provider_name} API Service Error")
        lines.append("")
        lines.append("Problem Description:")
        lines.append(f"  {str(self)}")
        
        # Add retry statistics if available
        if self.retry_stats:
            lines.append("")
            lines.append("Retry Statistics:")
            
            # Generation retries
            gen_retry = self.retry_stats.get('generation_retries', 0)
            gen_max = self.retry_stats.get('generation_max_retries', 0)
            if gen_retry > 0:
                lines.append(f"  • Generation Retries: {gen_retry}/{gen_max}")
            
            # HTTP retries
            http_retry = self.retry_stats.get('http_retries', 0)
            http_max = self.retry_stats.get('http_max_retries', 0)
            if http_retry > 0:
                lines.append(f"  • HTTP Retries: {http_retry}/{http_max}")
            
            # Total retry time
            retry_time = self.retry_stats.get('total_retry_time', 0)
            if retry_time > 0:
                lines.append(f"  • Retry Time: {retry_time:.1f}s")
            
            # Retry reasons
            retry_reasons = self.retry_stats.get('retry_reasons', [])
            if retry_reasons:
                lines.append(f"  • Retry Reasons: {', '.join(retry_reasons)}")
        
        if self.raw_response:
            lines.append("")
            lines.append("Actual Response:")
            preview = self.raw_response[:200] + "..." if len(self.raw_response) > 200 else self.raw_response
            lines.append(f"  {preview}")
        
        if self.debug_file:
            lines.append("")
            lines.append("Debug Information:")
            lines.append(f"  • Response Details: {self.debug_file}")
        
        if self.suggestions:
            lines.append("")
            lines.append("Suggested Actions:")
            for i, suggestion in enumerate(self.suggestions, 1):
                lines.append(f"  {i}. {suggestion}")
        
        return "\n".join(lines)
    
    @classmethod
    def create_with_retry_stats(cls, 
                               message: str,
                               provider_name: str,
                               generation_retries: int = 0,
                               generation_max_retries: int = 0,
                               http_retries: int = 0,
                               http_max_retries: int = 0,
                               total_retry_time: float = 0,
                               retry_reasons: Optional[List[str]] = None,
                               **kwargs) -> 'ProviderError':
        """Create a ProviderError with detailed retry statistics.
        
        Args:
            message: Error message
            provider_name: Provider name
            generation_retries: Number of generation retries performed
            generation_max_retries: Maximum generation retries allowed
            http_retries: Number of HTTP retries performed
            http_max_retries: Maximum HTTP retries allowed
            total_retry_time: Total time spent on retries
            retry_reasons: List of retry reasons
            **kwargs: Additional parameters for ProviderError
            
        Returns:
            ProviderError instance with retry statistics
        """
        retry_stats = {
            'generation_retries': generation_retries,
            'generation_max_retries': generation_max_retries,
            'http_retries': http_retries,
            'http_max_retries': http_max_retries,
            'total_retry_time': total_retry_time,
            'retry_reasons': retry_reasons or []
        }
        
        return cls(
            message=message,
            provider_name=provider_name,
            retry_stats=retry_stats,
            **kwargs
        )
    
    def add_retry_info(self, 
                      generation_retries: int = 0,
                      http_retries: int = 0,
                      retry_time: float = 0,
                      retry_reason: Optional[str] = None) -> None:
        """Add or update retry information to existing error.
        
        Args:
            generation_retries: Number of generation retries
            http_retries: Number of HTTP retries
            retry_time: Time spent on this retry
            retry_reason: Reason for retry
        """
        if not self.retry_stats:
            self.retry_stats = {}
        
        self.retry_stats['generation_retries'] = generation_retries
        self.retry_stats['http_retries'] = self.retry_stats.get('http_retries', 0) + http_retries
        self.retry_stats['total_retry_time'] = self.retry_stats.get('total_retry_time', 0) + retry_time
        
        if retry_reason:
            if 'retry_reasons' not in self.retry_stats:
                self.retry_stats['retry_reasons'] = []
            if retry_reason not in self.retry_stats['retry_reasons']:
                self.retry_stats['retry_reasons'].append(retry_reason)
    
    def save_debug_info(self, request_data: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Save debug information to file."""
        if not self.provider_name:
            return None
        
        try:
            debug_dir = Path("debug_responses")
            debug_dir.mkdir(exist_ok=True)
            
            timestamp_str = time.strftime("%Y%m%d_%H%M%S", time.localtime(self.timestamp))
            filename = f"{self.provider_name}_error_{timestamp_str}.json"
            filepath = debug_dir / filename
            
            debug_data = {
                "error_info": {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self.timestamp)),
                    "provider": self.provider_name,
                    "error_type": self.__class__.__name__,
                    "error_code": self.error_code,
                    "message": str(self)
                },
                "response": {
                    "content": self.raw_response,
                    "content_length": len(self.raw_response) if self.raw_response else 0
                }
            }
            
            if request_data:
                debug_data["request"] = request_data
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(debug_data, f, ensure_ascii=False, indent=2)
            
            self.debug_file = str(filepath)
            return str(filepath)
        except Exception:
            # Don't let debug saving failure break the main error flow
            return None


class ProviderNotFoundError(ProviderError):
    """Raised when a provider is not found."""
    pass


class ProviderConfigError(ProviderError):
    """Raised when provider configuration is invalid."""
    pass


class ProviderHealthCheckError(ProviderError):
    """Raised when provider health check fails."""
    pass


class ProviderGenerationError(ProviderError):
    """Raised when provider fails to generate content."""
    pass


class ProviderEmptyResponseError(ProviderError):
    """Raised when provider returns empty response."""
    
    def __init__(self, provider_name: str, attempt: int = 1, timeout_duration: Optional[int] = None):
        suggestions = [
            "Retry after waiting 30 seconds",
            f"Use alternative provider instead of {provider_name}",
            "Check network connection status"
        ]
        
        if timeout_duration:
            suggestions.append(f"Increase timeout --timeout {timeout_duration + 30}")
        
        message = f"{provider_name} API returned empty response on attempt {attempt}"
        if timeout_duration:
            message += f" (timeout after {timeout_duration}s)"
        
        super().__init__(
            message=message,
            provider_name=provider_name,
            suggestions=suggestions,
            error_code="EMPTY_RESPONSE"
        )


class ProviderInvalidFormatError(ProviderError):
    """Raised when provider returns invalid format."""
    
    def __init__(self, provider_name: str, expected_format: str, received_format: str, raw_content: str = ""):
        suggestions = [
            "Retry request (model output unstable)",
            f"Check if {provider_name} model supports structured output",
            "Use more stable provider"
        ]
        
        message = f"{provider_name} API returned invalid format (expected: {expected_format}, actual: {received_format})"
        
        super().__init__(
            message=message,
            provider_name=provider_name,
            raw_response=raw_content[:500] if raw_content else None,
            suggestions=suggestions,
            error_code="INVALID_FORMAT"
        )


class ProviderTimeoutError(ProviderError):
    """Raised when provider request times out."""
    
    def __init__(self, provider_name: str, timeout_duration: int, request_type: str = "request"):
        suggestions = [
            f"Increase timeout --timeout {timeout_duration + 30}",
            "Check network connection speed",
            f"Use faster {provider_name} model",
            "Retry later"
        ]
        
        message = f"{provider_name} API {request_type} timeout after {timeout_duration} seconds"
        
        super().__init__(
            message=message,
            provider_name=provider_name,
            suggestions=suggestions,
            error_code="TIMEOUT"
        )


class ProviderQuotaError(ProviderError):
    """Raised when provider quota is exceeded."""
    
    def __init__(self, provider_name: str, remaining_quota: int = 0):
        suggestions = [
            f"Recharge {provider_name} API quota",
            "Switch to alternative provider",
            "Wait for quota reset"
        ]
        
        if remaining_quota > 0:
            message = f"{provider_name} API quota insufficient (remaining: {remaining_quota})"
        else:
            message = f"{provider_name} API quota exhausted"
        
        super().__init__(
            message=message,
            provider_name=provider_name,
            suggestions=suggestions,
            error_code="QUOTA_EXCEEDED"
        )


class ProviderAuthError(ProviderError):
    """Raised when provider authentication fails."""
    
    def __init__(self, provider_name: str, status_code: Optional[int] = None):
        suggestions = [
            "Check API key in configuration file",
            f"Verify {provider_name} API key is valid",
            "Check if API key has expired"
        ]
        
        message = f"{provider_name} API authentication failed"
        if status_code:
            message += f" (status: {status_code})"
        
        super().__init__(
            message=message,
            provider_name=provider_name,
            suggestions=suggestions,
            error_code="AUTH_FAILED"
        )


class ProviderRateLimitError(ProviderError):
    """Raised when provider rate limit is exceeded."""
    
    def __init__(self, provider_name: str, reset_time: Optional[int] = None):
        suggestions = [
            "Reduce concurrency --workers 1",
            "Increase request interval"
        ]
        
        if reset_time:
            suggestions.append(f"Wait {reset_time} seconds before retry")
        else:
            suggestions.append("Retry later")
        
        message = f"{provider_name} API rate limit exceeded"
        if reset_time:
            message += f" (resets in {reset_time}s)"
        
        super().__init__(
            message=message,
            provider_name=provider_name,
            suggestions=suggestions,
            error_code="RATE_LIMIT"
        )


