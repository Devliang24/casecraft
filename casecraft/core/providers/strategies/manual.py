"""Manual provider mapping strategy."""

import re
from typing import Dict, List, Optional
from casecraft.core.providers.strategies.base import ProviderStrategy
from casecraft.models.api_spec import APIEndpoint


class ManualMappingStrategy(ProviderStrategy):
    """Assigns providers based on manual path-to-provider mappings."""
    
    def __init__(self, providers: List[str], mapping_str: str = None):
        """Initialize manual mapping strategy.
        
        Args:
            providers: List of available provider names
            mapping_str: Mapping string in format "path1:provider1,path2:provider2"
                        Supports wildcards: "/users/*:qwen,/products:glm"
        """
        super().__init__(providers)
        self.mappings: Dict[str, str] = {}
        self.patterns: List[tuple[re.Pattern, str]] = []
        self.default_provider = providers[0] if providers else None
        
        if mapping_str:
            self._parse_mapping(mapping_str)
    
    def _parse_mapping(self, mapping_str: str) -> None:
        """Parse mapping string into rules.
        
        Args:
            mapping_str: Mapping string to parse
        """
        if not mapping_str:
            return
        
        # Split by comma to get individual mappings
        for mapping in mapping_str.split(','):
            mapping = mapping.strip()
            if ':' not in mapping:
                continue
            
            path, provider = mapping.split(':', 1)
            path = path.strip()
            provider = provider.strip()
            
            # Validate provider exists
            if provider not in self.providers:
                raise ValueError(f"Provider '{provider}' not in available providers: {self.providers}")
            
            # Check if path contains wildcards
            if '*' in path or '?' in path:
                # Convert to regex pattern
                pattern = path.replace('*', '.*').replace('?', '.')
                pattern = f"^{pattern}$"
                self.patterns.append((re.compile(pattern), provider))
            else:
                # Exact match
                self.mappings[path] = provider
    
    def get_next_provider(self, endpoint: APIEndpoint) -> str:
        """Get provider for an endpoint based on manual mapping.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            Mapped provider name or default provider
        """
        if not self.providers:
            raise ValueError("No providers available")
        
        # Get endpoint path
        path = endpoint.path
        
        # Check exact matches first
        if path in self.mappings:
            return self.mappings[path]
        
        # Check pattern matches
        for pattern, provider in self.patterns:
            if pattern.match(path):
                return provider
        
        # Check if endpoint has method, try method+path combination
        if hasattr(endpoint, 'method'):
            method_path = f"{endpoint.method}:{path}"
            if method_path in self.mappings:
                return self.mappings[method_path]
        
        # Return default provider
        if self.default_provider:
            return self.default_provider
        
        raise ValueError(f"No mapping found for endpoint {path} and no default provider set")
    
    def add_mapping(self, path: str, provider: str) -> None:
        """Add a new mapping rule.
        
        Args:
            path: Path pattern
            provider: Provider name
        """
        if provider not in self.providers:
            raise ValueError(f"Provider '{provider}' not in available providers")
        
        if '*' in path or '?' in path:
            pattern = path.replace('*', '.*').replace('?', '.')
            pattern = f"^{pattern}$"
            self.patterns.append((re.compile(pattern), provider))
        else:
            self.mappings[path] = provider
    
    def set_default_provider(self, provider: str) -> None:
        """Set the default provider for unmapped endpoints.
        
        Args:
            provider: Default provider name
        """
        if provider not in self.providers:
            raise ValueError(f"Provider '{provider}' not in available providers")
        
        self.default_provider = provider
    
    def get_mappings_summary(self) -> Dict[str, any]:
        """Get a summary of current mappings.
        
        Returns:
            Dictionary with mapping information
        """
        return {
            "exact_mappings": self.mappings,
            "pattern_mappings": [(p.pattern, prov) for p, prov in self.patterns],
            "default_provider": self.default_provider,
            "available_providers": self.providers
        }