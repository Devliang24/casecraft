"""Base class for provider assignment strategies."""

from abc import ABC, abstractmethod
from typing import List
from casecraft.models.api_spec import APIEndpoint


class ProviderStrategy(ABC):
    """Abstract base class for provider assignment strategies."""
    
    def __init__(self, providers: List[str]):
        """Initialize strategy with list of providers.
        
        Args:
            providers: List of provider names
        """
        self.providers = providers
    
    @abstractmethod
    def get_next_provider(self, endpoint: APIEndpoint) -> str:
        """Get the next provider for an endpoint.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            Provider name
        """
        pass
    
    def reset(self) -> None:
        """Reset strategy state (optional)."""
        pass