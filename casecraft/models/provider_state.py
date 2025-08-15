"""Enhanced state models for provider tracking."""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ProviderPerformance(BaseModel):
    """Performance metrics for a provider."""
    
    total_requests: int = Field(default=0, description="Total generation requests")
    successful_requests: int = Field(default=0, description="Successful generations")
    failed_requests: int = Field(default=0, description="Failed generations")
    total_tokens: int = Field(default=0, description="Total tokens consumed")
    total_time_seconds: float = Field(default=0.0, description="Total processing time")
    avg_response_time: float = Field(default=0.0, description="Average response time")
    avg_tokens_per_request: float = Field(default=0.0, description="Average tokens per request")
    error_types: Dict[str, int] = Field(default_factory=dict, description="Error count by type")
    last_used: Optional[datetime] = Field(None, description="Last usage timestamp")
    
    def update_success(self, tokens: int, time_seconds: float) -> None:
        """Update metrics for successful request."""
        self.total_requests += 1
        self.successful_requests += 1
        self.total_tokens += tokens
        self.total_time_seconds += time_seconds
        self.last_used = datetime.now()
        self._recalculate_averages()
    
    def update_failure(self, error_type: str, time_seconds: float) -> None:
        """Update metrics for failed request."""
        self.total_requests += 1
        self.failed_requests += 1
        self.total_time_seconds += time_seconds
        self.error_types[error_type] = self.error_types.get(error_type, 0) + 1
        self.last_used = datetime.now()
        self._recalculate_averages()
    
    def _recalculate_averages(self) -> None:
        """Recalculate average metrics."""
        if self.total_requests > 0:
            self.avg_response_time = self.total_time_seconds / self.total_requests
        if self.successful_requests > 0:
            self.avg_tokens_per_request = self.total_tokens / self.successful_requests
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests


class FallbackEvent(BaseModel):
    """Record of a fallback event."""
    
    timestamp: datetime = Field(default_factory=datetime.now, description="Event timestamp")
    endpoint_id: str = Field(..., description="Endpoint that triggered fallback")
    primary_provider: str = Field(..., description="Primary provider that failed")
    fallback_provider: str = Field(..., description="Fallback provider used")
    error_type: str = Field(..., description="Type of error that triggered fallback")
    success: bool = Field(..., description="Whether fallback succeeded")


class CostEstimate(BaseModel):
    """Cost estimation for provider usage."""
    
    provider: str = Field(..., description="Provider name")
    tokens_used: int = Field(default=0, description="Total tokens consumed")
    estimated_cost: float = Field(default=0.0, description="Estimated cost in USD")
    cost_per_1k_tokens: float = Field(default=0.0, description="Cost per 1000 tokens")
    
    def calculate_cost(self) -> float:
        """Calculate cost based on tokens and rate."""
        if self.cost_per_1k_tokens > 0:
            self.estimated_cost = (self.tokens_used / 1000) * self.cost_per_1k_tokens
        return self.estimated_cost


class ProviderStatistics(BaseModel):
    """Comprehensive provider statistics."""
    
    performance: Dict[str, ProviderPerformance] = Field(
        default_factory=dict, 
        description="Performance metrics by provider"
    )
    fallback_events: List[FallbackEvent] = Field(
        default_factory=list,
        description="History of fallback events"
    )
    cost_estimates: Dict[str, CostEstimate] = Field(
        default_factory=dict,
        description="Cost estimates by provider"
    )
    provider_preferences: Dict[str, float] = Field(
        default_factory=dict,
        description="Provider preference scores (0-1)"
    )
    
    def update_provider_success(self, provider: str, tokens: int, time_seconds: float) -> None:
        """Update metrics for successful provider request."""
        if provider not in self.performance:
            self.performance[provider] = ProviderPerformance()
        self.performance[provider].update_success(tokens, time_seconds)
        
        # Update cost estimate
        if provider not in self.cost_estimates:
            self.cost_estimates[provider] = CostEstimate(provider=provider)
        self.cost_estimates[provider].tokens_used += tokens
    
    def update_provider_failure(self, provider: str, error_type: str, time_seconds: float) -> None:
        """Update metrics for failed provider request."""
        if provider not in self.performance:
            self.performance[provider] = ProviderPerformance()
        self.performance[provider].update_failure(error_type, time_seconds)
    
    def record_fallback(self, event: FallbackEvent) -> None:
        """Record a fallback event."""
        self.fallback_events.append(event)
        
        # Adjust provider preferences based on fallback
        if event.primary_provider in self.provider_preferences:
            # Decrease preference for failed provider
            self.provider_preferences[event.primary_provider] *= 0.95
        
        if event.success and event.fallback_provider in self.provider_preferences:
            # Increase preference for successful fallback
            self.provider_preferences[event.fallback_provider] = min(
                1.0, self.provider_preferences.get(event.fallback_provider, 0.5) * 1.05
            )
    
    def get_provider_ranking(self) -> List[tuple[str, float]]:
        """Get providers ranked by performance score."""
        scores = []
        
        for provider, perf in self.performance.items():
            # Calculate composite score
            success_rate = perf.success_rate
            avg_time = perf.avg_response_time if perf.avg_response_time > 0 else float('inf')
            preference = self.provider_preferences.get(provider, 0.5)
            
            # Composite score: 50% success rate, 30% speed, 20% preference
            speed_score = 1.0 / (1 + avg_time) if avg_time < float('inf') else 0
            score = (success_rate * 0.5) + (speed_score * 0.3) + (preference * 0.2)
            
            scores.append((provider, score))
        
        return sorted(scores, key=lambda x: x[1], reverse=True)
    
    def get_cost_summary(self) -> Dict[str, any]:
        """Get cost summary across all providers."""
        total_cost = sum(est.calculate_cost() for est in self.cost_estimates.values())
        total_tokens = sum(est.tokens_used for est in self.cost_estimates.values())
        
        return {
            "total_cost_usd": total_cost,
            "total_tokens": total_tokens,
            "by_provider": {
                provider: {
                    "tokens": est.tokens_used,
                    "cost": est.estimated_cost
                }
                for provider, est in self.cost_estimates.items()
            }
        }


# Cost rates for known providers (per 1000 tokens)
DEFAULT_COST_RATES = {
    "glm": {"input": 0.001, "output": 0.002},  # Example rates
    "qwen": {"input": 0.0008, "output": 0.0016},
    "local": {"input": 0.0, "output": 0.0},  # Free for local
}