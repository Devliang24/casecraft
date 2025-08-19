"""Configuration helper utilities."""

import os
from typing import Any, Optional
from casecraft.utils.constants import (
    PROVIDER_BASE_URLS, PROVIDER_MAX_WORKERS, DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_PROVIDER_TIMEOUT, DEFAULT_API_PARSE_TIMEOUT, DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE, DEFAULT_KEEP_DAYS, DEFAULT_OLLAMA_PORT, 
    DEFAULT_VLLM_PORT, DEFAULT_LOCAL_PORT
)


class ConfigHelper:
    """Helper for getting configuration with fallback to env vars and defaults."""
    
    @staticmethod
    def get_provider_url(provider: str, config_value: Optional[str] = None) -> str:
        """Get provider URL with fallback to env var and default.
        
        Priority: config > env > default
        """
        if config_value:
            return config_value
            
        env_key = f"CASECRAFT_{provider.upper()}_BASE_URL"
        env_value = os.getenv(env_key)
        if env_value:
            return env_value
            
        return PROVIDER_BASE_URLS.get(provider, '')
    
    @staticmethod
    def get_max_workers(provider: str, config_value: Optional[int] = None) -> int:
        """Get max workers with fallback."""
        if config_value:
            return config_value
            
        env_key = f"CASECRAFT_{provider.upper()}_MAX_WORKERS"
        env_value = os.getenv(env_key)
        if env_value:
            return int(env_value)
            
        return PROVIDER_MAX_WORKERS.get(provider, 1)
    
    @staticmethod
    def get_timeout(context: str = 'default', config_value: Optional[int] = None) -> int:
        """Get timeout with fallback.
        
        Args:
            context: 'default', 'provider', or 'api_parse'
            config_value: Override value from config
        """
        if config_value:
            return config_value
        
        env_key = f"CASECRAFT_{context.upper()}_TIMEOUT"
        env_value = os.getenv(env_key)
        if env_value:
            return int(env_value)
        
        timeout_defaults = {
            'default': DEFAULT_REQUEST_TIMEOUT,
            'provider': DEFAULT_PROVIDER_TIMEOUT,
            'api_parse': DEFAULT_API_PARSE_TIMEOUT,
        }
        return timeout_defaults.get(context, DEFAULT_REQUEST_TIMEOUT)
    
    @staticmethod
    def get_max_tokens(config_value: Optional[int] = None) -> int:
        """Get max tokens with fallback."""
        if config_value:
            return config_value
            
        env_value = os.getenv("CASECRAFT_MAX_TOKENS")
        if env_value:
            return int(env_value)
            
        return DEFAULT_MAX_TOKENS
    
    @staticmethod
    def get_temperature(config_value: Optional[float] = None) -> float:
        """Get temperature with fallback."""
        if config_value is not None:
            return config_value
            
        env_value = os.getenv("CASECRAFT_TEMPERATURE")
        if env_value:
            return float(env_value)
            
        return DEFAULT_TEMPERATURE
    
    @staticmethod
    def get_keep_days(config_value: Optional[int] = None) -> int:
        """Get keep days with fallback."""
        if config_value:
            return config_value
            
        env_value = os.getenv("CASECRAFT_KEEP_DAYS")
        if env_value:
            return int(env_value)
            
        return DEFAULT_KEEP_DAYS
    
    @staticmethod
    def get_local_port(service: str = 'default', config_value: Optional[int] = None) -> int:
        """Get local service port with fallback.
        
        Args:
            service: 'ollama', 'vllm', or 'default'
            config_value: Override value from config
        """
        if config_value:
            return config_value
        
        env_key = f"{service.upper()}_PORT"
        env_value = os.getenv(env_key)
        if env_value:
            return int(env_value)
        
        port_defaults = {
            'ollama': DEFAULT_OLLAMA_PORT,
            'vllm': DEFAULT_VLLM_PORT,
            'default': DEFAULT_LOCAL_PORT,
        }
        return port_defaults.get(service, DEFAULT_LOCAL_PORT)