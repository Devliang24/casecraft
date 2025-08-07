"""Random provider assignment strategy."""

import random
from typing import List, Optional

from casecraft.core.providers.strategies.base import ProviderStrategy
from casecraft.models.api_spec import APIEndpoint


class RandomStrategy(ProviderStrategy):
    """随机分配策略 - 为每个端点随机选择提供商."""
    
    def __init__(self, providers: List[str]):
        """Initialize random strategy.
        
        Args:
            providers: List of provider names
        """
        super().__init__(providers)
    
    def get_next_provider(self, endpoint: APIEndpoint) -> str:
        """Get randomly selected provider for endpoint.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            Selected provider name
        """
        return random.choice(self.providers)
    
    def reset(self) -> None:
        """Reset strategy state (no-op for random)."""
        pass  # Random strategy has no state to reset