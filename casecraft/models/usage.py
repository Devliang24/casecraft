"""Token usage and cost calculation models."""

from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
import time


@dataclass
class TokenUsage:
    """Token usage data for a single LLM API call."""
    
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    endpoint_id: str = ""
    retry_count: int = 0  # Number of retries for this specific call
    
    def __post_init__(self):
        """Validate and normalize token counts."""
        # Ensure total_tokens is consistent
        if self.total_tokens == 0 and (self.prompt_tokens > 0 or self.completion_tokens > 0):
            self.total_tokens = self.prompt_tokens + self.completion_tokens
        
        # Validate non-negative values
        if self.prompt_tokens < 0 or self.completion_tokens < 0 or self.total_tokens < 0:
            raise ValueError("Token counts must be non-negative")


@dataclass 
class TokenStatistics:
    """Aggregated token usage statistics."""
    
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    
    # Retry statistics
    total_retries: int = 0
    retry_attempts_by_endpoint: Dict[str, int] = None
    max_retries_for_single_endpoint: int = 0
    endpoints_with_retries: int = 0
    
    def __post_init__(self):
        """Initialize nested data structures."""
        if self.retry_attempts_by_endpoint is None:
            self.retry_attempts_by_endpoint = {}
    
    def add_usage(self, usage: TokenUsage, success: bool = True) -> None:
        """Add token usage from a single API call.
        
        Args:
            usage: Token usage data
            success: Whether the API call was successful
        """
        self.total_prompt_tokens += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens
        self.total_calls += 1
        
        if success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1
        
        # Record retry statistics
        if usage.retry_count > 0:
            self.total_retries += usage.retry_count
            endpoint_id = usage.endpoint_id or "unknown"
            
            # Track retries by endpoint
            if endpoint_id not in self.retry_attempts_by_endpoint:
                self.retry_attempts_by_endpoint[endpoint_id] = 0
                self.endpoints_with_retries += 1
            
            self.retry_attempts_by_endpoint[endpoint_id] += usage.retry_count
            
            # Update max retries for single endpoint
            endpoint_total_retries = self.retry_attempts_by_endpoint[endpoint_id]
            self.max_retries_for_single_endpoint = max(
                self.max_retries_for_single_endpoint, 
                endpoint_total_retries
            )
    
    def get_average_tokens_per_call(self) -> float:
        """Get average total tokens per successful call."""
        if self.successful_calls == 0:
            return 0.0
        return self.total_tokens / self.successful_calls
    
    def get_success_rate(self) -> float:
        """Get success rate of API calls."""
        if self.total_calls == 0:
            return 0.0
        return self.successful_calls / self.total_calls
    
    def get_average_retries_per_endpoint(self) -> float:
        """Get average number of retries per endpoint that had retries."""
        if self.endpoints_with_retries == 0:
            return 0.0
        return self.total_retries / self.endpoints_with_retries
    
    def get_retry_summary(self) -> Dict[str, Any]:
        """Get comprehensive retry statistics summary.
        
        Returns:
            Dictionary with retry statistics
        """
        return {
            "total_retries": self.total_retries,
            "endpoints_with_retries": self.endpoints_with_retries,
            "max_retries_for_single_endpoint": self.max_retries_for_single_endpoint,
            "average_retries_per_endpoint": self.get_average_retries_per_endpoint(),
            "retry_rate": self.endpoints_with_retries / max(self.total_calls, 1),
            "most_retried_endpoints": self._get_most_retried_endpoints(3)
        }
    
    def _get_most_retried_endpoints(self, limit: int = 3) -> list:
        """Get endpoints with most retries.
        
        Args:
            limit: Maximum number of endpoints to return
            
        Returns:
            List of (endpoint_id, retry_count) tuples
        """
        if not self.retry_attempts_by_endpoint:
            return []
        
        sorted_endpoints = sorted(
            self.retry_attempts_by_endpoint.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return sorted_endpoints[:limit]


@dataclass
class RetryAttempt:
    """Record of a single retry attempt."""
    
    attempt_number: int  # 1-based attempt number
    layer: str  # "HTTP", "generation", "provider"
    reason: str  # Reason for retry
    start_time: float  # Start timestamp
    end_time: Optional[float] = None  # End timestamp (when retry completes)
    success: bool = False  # Whether this attempt succeeded
    error_message: Optional[str] = None  # Error message if failed
    wait_time: Optional[float] = None  # Time waited before this retry
    
    @property
    def duration(self) -> float:
        """Get duration of this attempt."""
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time
    
    def complete(self, success: bool, error_message: Optional[str] = None) -> None:
        """Mark this attempt as completed.
        
        Args:
            success: Whether the attempt succeeded
            error_message: Error message if failed
        """
        self.end_time = time.time()
        self.success = success
        self.error_message = error_message


@dataclass 
class RetryTracker:
    """Comprehensive retry statistics tracker."""
    
    endpoint_id: str = ""
    operation_start_time: float = field(default_factory=time.time)
    
    # Layered retry attempts
    http_attempts: List[RetryAttempt] = field(default_factory=list)
    generation_attempts: List[RetryAttempt] = field(default_factory=list)
    provider_attempts: List[RetryAttempt] = field(default_factory=list)
    
    # Overall statistics
    total_operation_time: float = 0.0
    total_retry_time: float = 0.0
    total_wait_time: float = 0.0
    
    def start_attempt(self, layer: str, reason: str, attempt_number: int, wait_time: Optional[float] = None) -> RetryAttempt:
        """Start tracking a new retry attempt.
        
        Args:
            layer: Layer of retry ("HTTP", "generation", "provider")
            reason: Reason for retry
            attempt_number: 1-based attempt number
            wait_time: Time waited before this attempt
            
        Returns:
            RetryAttempt object for tracking this attempt
        """
        attempt = RetryAttempt(
            attempt_number=attempt_number,
            layer=layer,
            reason=reason,
            start_time=time.time(),
            wait_time=wait_time
        )
        
        # Add to appropriate list
        if layer.lower() == "http":
            self.http_attempts.append(attempt)
        elif layer.lower() == "generation":
            self.generation_attempts.append(attempt)
        elif layer.lower() == "provider":
            self.provider_attempts.append(attempt)
        
        # Track wait time
        if wait_time:
            self.total_wait_time += wait_time
        
        return attempt
    
    def complete_operation(self) -> None:
        """Mark the entire operation as completed."""
        self.total_operation_time = time.time() - self.operation_start_time
        
        # Calculate total retry time (excluding initial attempt)
        self.total_retry_time = sum(
            attempt.duration for attempts in [self.http_attempts, self.generation_attempts, self.provider_attempts]
            for attempt in attempts if attempt.attempt_number > 1
        )
    
    def get_layer_stats(self, layer: str) -> Dict[str, Any]:
        """Get statistics for a specific retry layer.
        
        Args:
            layer: Layer to get stats for
            
        Returns:
            Dictionary with layer statistics
        """
        if layer.lower() == "http":
            attempts = self.http_attempts
        elif layer.lower() == "generation":
            attempts = self.generation_attempts
        elif layer.lower() == "provider":
            attempts = self.provider_attempts
        else:
            return {}
        
        if not attempts:
            return {"total_attempts": 0, "retries": 0, "success_rate": 0.0}
        
        total_attempts = len(attempts)
        retries = total_attempts - 1  # Exclude initial attempt
        successful_attempts = sum(1 for attempt in attempts if attempt.success)
        failed_attempts = total_attempts - successful_attempts
        
        return {
            "total_attempts": total_attempts,
            "retries": retries,
            "successful_attempts": successful_attempts,
            "failed_attempts": failed_attempts,
            "success_rate": successful_attempts / total_attempts if total_attempts > 0 else 0.0,
            "total_time": sum(attempt.duration for attempt in attempts),
            "total_wait_time": sum(attempt.wait_time or 0 for attempt in attempts),
            "average_attempt_time": sum(attempt.duration for attempt in attempts) / total_attempts if total_attempts > 0 else 0.0,
            "reasons": [attempt.reason for attempt in attempts if attempt.attempt_number > 1]
        }
    
    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive retry statistics across all layers.
        
        Returns:
            Dictionary with complete retry statistics
        """
        http_stats = self.get_layer_stats("http")
        generation_stats = self.get_layer_stats("generation")
        provider_stats = self.get_layer_stats("provider")
        
        total_retries = http_stats.get("retries", 0) + generation_stats.get("retries", 0) + provider_stats.get("retries", 0)
        total_attempts = http_stats.get("total_attempts", 0) + generation_stats.get("total_attempts", 0) + provider_stats.get("total_attempts", 0)
        
        return {
            "endpoint_id": self.endpoint_id,
            "total_operation_time": self.total_operation_time,
            "total_retry_time": self.total_retry_time,
            "total_wait_time": self.total_wait_time,
            "retry_time_percentage": (self.total_retry_time / self.total_operation_time * 100) if self.total_operation_time > 0 else 0,
            "wait_time_percentage": (self.total_wait_time / self.total_operation_time * 100) if self.total_operation_time > 0 else 0,
            "total_retries": total_retries,
            "total_attempts": total_attempts,
            "layers": {
                "http": http_stats,
                "generation": generation_stats,
                "provider": provider_stats
            },
            "timeline": self._get_retry_timeline()
        }
    
    def _get_retry_timeline(self) -> List[Dict[str, Any]]:
        """Get chronological timeline of all retry attempts.
        
        Returns:
            List of retry events in chronological order
        """
        all_attempts = []
        
        # Collect all attempts
        for layer, attempts in [("HTTP", self.http_attempts), ("Generation", self.generation_attempts), ("Provider", self.provider_attempts)]:
            for attempt in attempts:
                all_attempts.append({
                    "layer": layer,
                    "attempt_number": attempt.attempt_number,
                    "reason": attempt.reason,
                    "start_time": attempt.start_time,
                    "duration": attempt.duration,
                    "success": attempt.success,
                    "wait_time": attempt.wait_time
                })
        
        # Sort by start time
        all_attempts.sort(key=lambda x: x["start_time"])
        
        return all_attempts
    
    def get_summary_message(self) -> str:
        """Get human-readable summary of retry statistics.
        
        Returns:
            Summary string for logging/display
        """
        stats = self.get_comprehensive_stats()
        
        if stats["total_retries"] == 0:
            return f"✅ Operation completed successfully without retries in {stats['total_operation_time']:.1f}s"
        
        parts = [
            f"Operation completed after {stats['total_retries']} retries in {stats['total_operation_time']:.1f}s",
            f"({stats['retry_time_percentage']:.1f}% retry time, {stats['wait_time_percentage']:.1f}% wait time)"
        ]
        
        layer_info = []
        for layer, layer_stats in stats["layers"].items():
            if layer_stats.get("retries", 0) > 0:
                layer_info.append(f"{layer}: {layer_stats['retries']} retries")
        
        if layer_info:
            parts.append(f"Breakdown: {', '.join(layer_info)}")
        
        return " | ".join(parts)