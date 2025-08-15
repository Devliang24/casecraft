"""Configuration management for multiple LLM providers."""

import os
from typing import Any, Dict, List, Optional
import logging

from casecraft.core.management.config_manager import ConfigManager, ConfigError
from casecraft.models.provider_config import ProviderConfig, MultiProviderConfig
from casecraft.core.providers.base import ProviderConfig as BaseProviderConfig


class MultiProviderConfigManager(ConfigManager):
    """Manages configuration for multiple LLM providers."""
    
    def __init__(self, load_env: bool = True):
        """Initialize multi-provider configuration manager.
        
        Args:
            load_env: Whether to automatically load .env file
        """
        super().__init__(load_env)
        self.logger = logging.getLogger("config.multi_provider")
    
    def get_multi_provider_config(self) -> MultiProviderConfig:
        """Get multi-provider configuration from environment variables.
        
        Returns:
            Multi-provider configuration
        """
        config = MultiProviderConfig()
        
        # Get list of providers
        providers_str = os.getenv("CASECRAFT_PROVIDERS", "")
        if providers_str:
            config.providers = [p.strip() for p in providers_str.split(",") if p.strip()]
        
        # Get provider strategy
        strategy = os.getenv("CASECRAFT_PROVIDER_STRATEGY", "round_robin")
        config.strategy = strategy
        
        # Get fallback settings
        fallback_enabled = os.getenv("CASECRAFT_FALLBACK_ENABLED", "true")
        config.fallback_enabled = fallback_enabled.lower() == "true"
        
        fallback_chain_str = os.getenv("CASECRAFT_FALLBACK_CHAIN", "")
        if fallback_chain_str:
            config.fallback_chain = [p.strip() for p in fallback_chain_str.split(",") if p.strip()]
        
        # Parse individual provider configurations
        config.configs = self._parse_provider_configs(config.providers)
        
        return config
    
    def _parse_provider_configs(self, providers: List[str], workers: Optional[int] = None) -> Dict[str, ProviderConfig]:
        """Parse configuration for each provider.
        
        Args:
            providers: List of provider names
            workers: Number of workers from CLI (if provided)
            
        Returns:
            Dictionary of provider configurations
        """
        configs = {}
        
        for provider in providers:
            provider_upper = provider.upper()
            
            # Create provider config
            provider_config = ProviderConfig(
                name=provider,
                model=os.getenv(f"CASECRAFT_{provider_upper}_MODEL", ""),
                api_key=os.getenv(f"CASECRAFT_{provider_upper}_API_KEY"),
                base_url=os.getenv(f"CASECRAFT_{provider_upper}_BASE_URL"),
                timeout=self._parse_int(f"CASECRAFT_{provider_upper}_TIMEOUT", 60),
                max_retries=self._parse_int(f"CASECRAFT_{provider_upper}_MAX_RETRIES", 3),
                temperature=self._parse_float(f"CASECRAFT_{provider_upper}_TEMPERATURE", 0.7),
                stream=self._parse_bool(f"CASECRAFT_{provider_upper}_STREAM", False),
                workers=workers if workers is not None else 1  # Use CLI value if provided, else default to 1
            )
            
            # Add any extra provider-specific settings
            extra_settings = self._get_provider_extra_settings(provider_upper)
            for key, value in extra_settings.items():
                setattr(provider_config, key, value)
            
            configs[provider] = provider_config
        
        return configs
    
    def _get_provider_extra_settings(self, provider_upper: str) -> Dict[str, Any]:
        """Get extra provider-specific settings.
        
        Args:
            provider_upper: Provider name in uppercase
            
        Returns:
            Dictionary of extra settings
        """
        extra = {}
        
        # Check for provider-specific settings
        prefix = f"CASECRAFT_{provider_upper}_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                # Skip known settings
                known_suffixes = [
                    "MODEL", "API_KEY", "BASE_URL", "TIMEOUT",
                    "MAX_RETRIES", "TEMPERATURE", "STREAM", "WORKERS"
                ]
                suffix = key[len(prefix):]
                if suffix not in known_suffixes:
                    # Add as extra setting
                    setting_name = suffix.lower()
                    extra[setting_name] = value
        
        return extra
    
    def _parse_int(self, env_key: str, default: int) -> int:
        """Parse integer from environment variable.
        
        Args:
            env_key: Environment variable key
            default: Default value
            
        Returns:
            Parsed integer value
        """
        value = os.getenv(env_key)
        if value and value.isdigit():
            return int(value)
        return default
    
    def _parse_float(self, env_key: str, default: float) -> float:
        """Parse float from environment variable.
        
        Args:
            env_key: Environment variable key
            default: Default value
            
        Returns:
            Parsed float value
        """
        value = os.getenv(env_key)
        if value:
            try:
                return float(value)
            except ValueError:
                pass
        return default
    
    def _parse_bool(self, env_key: str, default: bool) -> bool:
        """Parse boolean from environment variable.
        
        Args:
            env_key: Environment variable key
            default: Default value
            
        Returns:
            Parsed boolean value
        """
        value = os.getenv(env_key)
        if value:
            return value.lower() in ("true", "1", "yes", "on")
        return default
    
    def validate_provider_specified(
        self,
        provider: Optional[str] = None,
        providers: Optional[List[str]] = None,
        provider_map: Optional[Dict[str, str]] = None
    ) -> None:
        """Validate that at least one provider is specified.
        
        Args:
            provider: Single provider name
            providers: List of provider names
            provider_map: Provider mapping
            
        Raises:
            ConfigError: If no provider is specified
        """
        if not any([provider, providers, provider_map]):
            # Check environment variables as fallback
            env_providers = os.getenv("CASECRAFT_PROVIDERS")
            env_provider = os.getenv("CASECRAFT_PROVIDER")
            
            if not any([env_providers, env_provider]):
                raise ConfigError(
                    "必须指定 LLM 提供商。请使用以下选项之一：\n"
                    "  --provider <name>：指定单个提供商\n"
                    "  --providers <list>：指定多个提供商列表\n"
                    "  --provider-map <mapping>：指定端点到提供商的映射\n"
                    "\n或设置环境变量：\n"
                    "  CASECRAFT_PROVIDER=glm\n"
                    "  CASECRAFT_PROVIDERS=glm,qwen,kimi\n"
                )
    
    def convert_to_base_config(self, provider_config: ProviderConfig) -> BaseProviderConfig:
        """Convert pydantic config to base provider config.
        
        Args:
            provider_config: Pydantic provider configuration
            
        Returns:
            Base provider configuration
        """
        return BaseProviderConfig(
            name=provider_config.name,
            model=provider_config.model,
            api_key=provider_config.api_key,
            base_url=provider_config.base_url,
            timeout=provider_config.timeout,
            max_retries=provider_config.max_retries,
            temperature=provider_config.temperature,
            stream=provider_config.stream,
            workers=provider_config.workers,
            **provider_config.dict(exclude={
                "name", "model", "api_key", "base_url",
                "timeout", "max_retries", "temperature", "stream", "workers"
            })
        )