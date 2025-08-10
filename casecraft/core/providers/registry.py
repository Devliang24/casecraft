"""Provider registry for managing LLM providers."""

from typing import Dict, Type, List, Optional
import logging

from casecraft.core.providers.base import LLMProvider, ProviderConfig
from casecraft.core.providers.exceptions import ProviderNotFoundError, ProviderConfigError


class ProviderRegistry:
    """Registry for managing LLM providers."""
    
    _providers: Dict[str, Type[LLMProvider]] = {}
    _instances: Dict[str, LLMProvider] = {}
    _logger = logging.getLogger("provider.registry")
    
    @classmethod
    def register(cls, name: str, provider_class: Type[LLMProvider]) -> None:
        """Register a provider class.
        
        Args:
            name: Provider name
            provider_class: Provider class type
        """
        if not issubclass(provider_class, LLMProvider):
            raise TypeError(f"{provider_class} must be a subclass of LLMProvider")
        
        cls._providers[name.lower()] = provider_class
        cls._logger.debug(f"Registered provider: {name}")
    
    @classmethod
    def get_provider(cls, name: str, config: Optional[ProviderConfig] = None) -> LLMProvider:
        """Get a provider instance (singleton pattern).
        
        Args:
            name: Provider name
            config: Provider configuration (required for first instantiation)
            
        Returns:
            Provider instance
            
        Raises:
            ProviderNotFoundError: If provider is not registered
            ProviderConfigError: If configuration is invalid
        """
        name_lower = name.lower()
        
        # Check if instance already exists
        if name_lower in cls._instances:
            return cls._instances[name_lower]
        
        # Check if provider is registered
        if name_lower not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise ProviderNotFoundError(
                f"Provider '{name}' not found. Available providers: {available}"
            )
        
        # Config is required for first instantiation
        if config is None:
            raise ProviderConfigError(
                f"Configuration required for first instantiation of provider '{name}'"
            )
        
        # Create new instance
        provider_class = cls._providers[name_lower]
        try:
            instance = provider_class(config)
            
            # Validate configuration
            if not instance.validate_config():
                raise ProviderConfigError(f"Invalid configuration for provider '{name}'")
            
            cls._instances[name_lower] = instance
            cls._logger.info(f"Instantiated provider: {name}")
            return instance
            
        except Exception as e:
            raise ProviderConfigError(f"Failed to instantiate provider '{name}': {e}")
    
    @classmethod
    def list_available(cls) -> List[str]:
        """List all available providers.
        
        Returns:
            List of available provider names
        """
        return list(cls._providers.keys())
    
    @classmethod
    def list_instances(cls) -> List[str]:
        """List all instantiated providers.
        
        Returns:
            List of instantiated provider names
        """
        return list(cls._instances.keys())
    
    @classmethod
    def clear_instances(cls) -> None:
        """Clear all provider instances (for testing)."""
        cls._instances.clear()
        cls._logger.debug("Cleared all provider instances")
    
    @classmethod
    def unregister(cls, name: str) -> None:
        """Unregister a provider (for testing).
        
        Args:
            name: Provider name to unregister
        """
        name_lower = name.lower()
        if name_lower in cls._providers:
            del cls._providers[name_lower]
            cls._logger.debug(f"Unregistered provider: {name}")
        
        if name_lower in cls._instances:
            del cls._instances[name_lower]
    
    @classmethod
    async def close_all(cls) -> None:
        """Close all provider instances."""
        for name, instance in cls._instances.items():
            try:
                await instance.close()
                cls._logger.debug(f"Closed provider: {name}")
            except Exception as e:
                cls._logger.error(f"Error closing provider {name}: {e}")