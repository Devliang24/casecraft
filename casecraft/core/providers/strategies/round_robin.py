"""Round-robin provider assignment strategy."""

from typing import List
from casecraft.core.providers.strategies.base import ProviderStrategy
from casecraft.models.api_spec import APIEndpoint


class RoundRobinStrategy(ProviderStrategy):
    """Assigns providers in round-robin fashion."""
    
    def __init__(self, providers: List[str]):
        """Initialize round-robin strategy.
        
        Args:
            providers: List of provider names
        """
        super().__init__(providers)
        self.current_index = 0
    
    def get_next_provider(self, endpoint: APIEndpoint) -> str:
        """Get the next provider in round-robin order.
        
        Args:
            endpoint: API endpoint (not used in round-robin)
            
        Returns:
            Provider name
        """
        if not self.providers:
            raise ValueError("No providers available")
        
        provider = self.providers[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.providers)
        return provider
    
    def reset(self) -> None:
        """Reset to the first provider."""
        self.current_index = 0