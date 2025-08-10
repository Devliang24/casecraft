"""Complexity-based provider assignment strategy."""

from typing import List, Dict, Optional

from casecraft.core.providers.strategies.base import ProviderStrategy
from casecraft.models.api_spec import APIEndpoint


class ComplexityBasedStrategy(ProviderStrategy):
    """基于复杂度的分配策略 - 根据端点复杂度选择合适的提供商.
    
    复杂端点分配给高能力提供商，简单端点分配给低成本提供商。
    """
    
    def __init__(self, providers: List[str], complexity_mapping: Optional[Dict[str, str]] = None):
        """Initialize complexity-based strategy.
        
        Args:
            providers: List of provider names
            complexity_mapping: Optional mapping of complexity levels to providers
                               Default: {"simple": local, "medium": qwen/kimi, "complex": glm}
        """
        super().__init__(providers)
        
        # Default complexity mapping based on provider capabilities
        self.complexity_mapping = complexity_mapping or self._get_default_mapping()
    
    def _get_default_mapping(self) -> Dict[str, str]:
        """Get default complexity to provider mapping.
        
        Returns:
            Default mapping dictionary
        """
        mapping = {}
        
        # Prefer local for simple endpoints (low cost)
        if "local" in self.providers:
            mapping["simple"] = "local"
        elif "qwen" in self.providers:
            mapping["simple"] = "qwen"
        else:
            mapping["simple"] = self.providers[0]
        
        # Prefer qwen/kimi for medium complexity (balanced)
        if "qwen" in self.providers:
            mapping["medium"] = "qwen"
        elif "kimi" in self.providers:
            mapping["medium"] = "kimi"
        elif "local" in self.providers:
            mapping["medium"] = "local"
        else:
            mapping["medium"] = self.providers[0]
        
        # Prefer glm for complex endpoints (high accuracy)
        if "glm" in self.providers:
            mapping["complex"] = "glm"
        elif "kimi" in self.providers:
            mapping["complex"] = "kimi"
        else:
            mapping["complex"] = self.providers[0]
        
        return mapping
    
    def get_next_provider(self, endpoint: APIEndpoint) -> str:
        """Get provider based on endpoint complexity.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            Selected provider name
        """
        complexity = self._calculate_complexity(endpoint)
        return self.complexity_mapping.get(complexity, self.providers[0])
    
    def _calculate_complexity(self, endpoint: APIEndpoint) -> str:
        """Calculate endpoint complexity.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            Complexity level: "simple", "medium", or "complex"
        """
        score = 0
        
        # Method complexity
        if endpoint.method in ["POST", "PUT", "PATCH"]:
            score += 3
        elif endpoint.method == "DELETE":
            score += 2
        else:  # GET, HEAD, OPTIONS
            score += 1
        
        # Parameter complexity
        if endpoint.path_params:
            score += len(endpoint.path_params)
        
        if endpoint.query_params:
            score += len(endpoint.query_params)
        
        if endpoint.headers:
            # Authentication headers add complexity
            auth_headers = [h for h in endpoint.headers if h.name.lower() in ["authorization", "x-api-key"]]
            score += len(auth_headers) * 2
            score += len(endpoint.headers) - len(auth_headers)
        
        # Request body complexity
        if endpoint.request_body:
            if hasattr(endpoint.request_body, 'required') and endpoint.request_body.required:
                score += 2
            
            # Check for nested objects in schema (safely)
            if hasattr(endpoint.request_body, 'content'):
                try:
                    for content_type, media_type in endpoint.request_body.content.items():
                        if hasattr(media_type, 'schema'):
                            schema = media_type.schema
                            if hasattr(schema, 'properties'):
                                # Count nested properties
                                for prop_name, prop_schema in schema.properties.items():
                                    if hasattr(prop_schema, 'type'):
                                        if prop_schema.type == 'object':
                                            score += 2
                                        elif prop_schema.type == 'array':
                                            score += 1
                except (AttributeError, TypeError):
                    # If content is not iterable or has issues, skip
                    pass
        
        # Response complexity (multiple response codes)
        if endpoint.responses:
            score += len(endpoint.responses) - 1  # -1 because one response is expected
        
        # Determine complexity level
        if score <= 5:
            return "simple"
        elif score <= 10:
            return "medium"
        else:
            return "complex"
    
    def reset(self) -> None:
        """Reset strategy state (no-op for complexity-based)."""
        pass  # Complexity-based strategy has no state to reset