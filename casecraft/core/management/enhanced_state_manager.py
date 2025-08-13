"""Enhanced state management with provider statistics."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
import time

import aiofiles
from pydantic import ValidationError

from casecraft.models.api_spec import APIEndpoint, APISpecification
from casecraft.models.state import CaseCraftState, EndpointState, ProjectConfig, ProcessingStatistics
from casecraft.models.provider_state import (
    ProviderStatistics, 
    FallbackEvent,
    CostEstimate,
    DEFAULT_COST_RATES
)
from casecraft.core.management.state_manager import StateManager, StateError


class EnhancedStateManager(StateManager):
    """Enhanced state manager with provider statistics tracking."""
    
    def __init__(self, state_file_path: Optional[Path] = None):
        """Initialize enhanced state manager.
        
        Args:
            state_file_path: Optional custom path to state file.
                           Defaults to .casecraft_state.json in current directory
        """
        super().__init__(state_file_path)
        self.provider_stats = ProviderStatistics()
        self._request_start_times: Dict[str, float] = {}
    
    async def load_state(self) -> CaseCraftState:
        """Load state from file including provider statistics.
        
        Returns:
            Loaded state with provider statistics
        """
        state = await super().load_state()
        
        # Use provider_stats from unified state if available
        if state.provider_stats:
            self.provider_stats = state.provider_stats
        else:
            # Initialize new provider stats if not present
            self.provider_stats = ProviderStatistics()
            state.provider_stats = self.provider_stats
        
        # Initialize cost rates for known providers
        for provider, rates in DEFAULT_COST_RATES.items():
            if provider not in self.provider_stats.cost_estimates:
                self.provider_stats.cost_estimates[provider] = CostEstimate(
                    provider=provider,
                    cost_per_1k_tokens=(rates["input"] + rates["output"]) / 2
                )
        
        return state
    
    async def save_state(self, state: CaseCraftState) -> None:
        """Save state to file including provider statistics.
        
        Args:
            state: State to save
        """
        # Update provider_stats in state before saving
        state.provider_stats = self.provider_stats
        await super().save_state(state)
    
    def start_provider_request(self, provider: str, endpoint_id: str) -> None:
        """Mark the start of a provider request for timing.
        
        Args:
            provider: Provider name
            endpoint_id: Endpoint being processed
        """
        key = f"{provider}:{endpoint_id}"
        self._request_start_times[key] = time.time()
    
    def complete_provider_request(
        self, 
        provider: str, 
        endpoint_id: str,
        success: bool,
        tokens: int = 0,
        error_type: Optional[str] = None
    ) -> None:
        """Mark completion of a provider request and update statistics.
        
        Args:
            provider: Provider name
            endpoint_id: Endpoint that was processed
            success: Whether request succeeded
            tokens: Tokens consumed (if successful)
            error_type: Type of error (if failed)
        """
        key = f"{provider}:{endpoint_id}"
        start_time = self._request_start_times.get(key)
        
        if start_time:
            elapsed = time.time() - start_time
            del self._request_start_times[key]
            
            if success:
                self.provider_stats.update_provider_success(provider, tokens, elapsed)
            else:
                self.provider_stats.update_provider_failure(
                    provider, 
                    error_type or "unknown",
                    elapsed
                )
    
    def record_fallback(
        self,
        endpoint_id: str,
        primary_provider: str,
        fallback_provider: str,
        error_type: str,
        success: bool
    ) -> None:
        """Record a fallback event.
        
        Args:
            endpoint_id: Endpoint that triggered fallback
            primary_provider: Provider that failed
            fallback_provider: Fallback provider used
            error_type: Type of error
            success: Whether fallback succeeded
        """
        event = FallbackEvent(
            endpoint_id=endpoint_id,
            primary_provider=primary_provider,
            fallback_provider=fallback_provider,
            error_type=error_type,
            success=success
        )
        self.provider_stats.record_fallback(event)
    
    def get_provider_recommendations(self) -> List[str]:
        """Get recommended provider order based on performance.
        
        Returns:
            List of provider names ordered by performance
        """
        ranking = self.provider_stats.get_provider_ranking()
        return [provider for provider, _ in ranking]
    
    def get_statistics_summary(self) -> Dict:
        """Get comprehensive statistics summary.
        
        Returns:
            Dictionary with statistics summary
        """
        # Get base statistics
        base_stats = {}
        if self._state:
            base_stats = {
                "total_endpoints": self._state.statistics.total_endpoints,
                "generated_count": self._state.statistics.generated_count,
                "skipped_count": self._state.statistics.skipped_count,
                "failed_count": self._state.statistics.failed_count,
            }
        
        # Add provider statistics
        provider_summary = {}
        for provider, perf in self.provider_stats.performance.items():
            provider_summary[provider] = {
                "requests": perf.total_requests,
                "success_rate": f"{perf.success_rate:.1%}",
                "avg_response_time": f"{perf.avg_response_time:.2f}s",
                "avg_tokens": f"{perf.avg_tokens_per_request:.0f}",
                "total_tokens": perf.total_tokens
            }
        
        # Add cost summary (using simple estimates from provider stats)
        cost_summary = self.provider_stats.get_cost_summary()
        
        # Add fallback statistics
        fallback_summary = {
            "total_fallbacks": len(self.provider_stats.fallback_events),
            "successful_fallbacks": sum(
                1 for e in self.provider_stats.fallback_events if e.success
            )
        }
        
        return {
            "generation": base_stats,
            "providers": provider_summary,
            "costs": cost_summary,
            "fallbacks": fallback_summary,
            "recommendations": self.get_provider_recommendations()[:3]  # Top 3
        }
    
    def print_statistics_report(self) -> None:
        """Print a formatted statistics report to console."""
        summary = self.get_statistics_summary()
        
        print("\n" + "="*60)
        print("📊 CaseCraft Statistics Report")
        print("="*60)
        
        # Generation statistics
        if summary.get("generation"):
            print("\n📝 Generation Summary:")
            gen = summary["generation"]
            print(f"  • Total Endpoints: {gen.get('total_endpoints', 0)}")
            print(f"  • Generated: {gen.get('generated_count', 0)}")
            print(f"  • Skipped: {gen.get('skipped_count', 0)}")
            print(f"  • Failed: {gen.get('failed_count', 0)}")
        
        # Provider performance
        if summary.get("providers"):
            print("\n🚀 Provider Performance:")
            for provider, stats in summary["providers"].items():
                print(f"\n  {provider}:")
                print(f"    • Requests: {stats['requests']}")
                print(f"    • Success Rate: {stats['success_rate']}")
                print(f"    • Avg Response: {stats['avg_response_time']}")
                print(f"    • Avg Tokens: {stats['avg_tokens']}")
        
        # Cost summary
        # Token summary
        if summary.get("providers"):
            total_tokens = sum(perf["total_tokens"] for perf in summary["providers"].values())
            if total_tokens > 0:
                print(f"\n📊 Token Usage:")
                print(f"  • Total Tokens: {total_tokens:,}")
                if len(summary["providers"]) > 1:
                    print("  • By Provider:")
                    for provider, stats in summary["providers"].items():
                        print(f"    - {provider}: {stats['total_tokens']:,} tokens")
        
        # Fallback statistics
        if summary.get("fallbacks"):
            fb = summary["fallbacks"]
            print(f"\n🔄 Fallback Statistics:")
            print(f"  • Total Fallbacks: {fb['total_fallbacks']}")
            print(f"  • Successful: {fb['successful_fallbacks']}")
        
        # Recommendations
        if summary.get("recommendations"):
            print(f"\n⭐ Recommended Providers (by performance):")
            for i, provider in enumerate(summary["recommendations"], 1):
                print(f"  {i}. {provider}")
        
        print("\n" + "="*60 + "\n")