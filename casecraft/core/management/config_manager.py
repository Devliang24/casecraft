"""Configuration management for CaseCraft."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import ValidationError
from dotenv import load_dotenv

from casecraft.models.config import CaseCraftConfig


class ConfigError(Exception):
    """Configuration related errors."""
    pass


class ConfigManager:
    """Manages CaseCraft configuration from environment variables and .env files."""
    
    def __init__(self, load_env: bool = True):
        """Initialize configuration manager.
        
        Args:
            load_env: Whether to automatically load .env file
        """
        # Load .env file if it exists
        if load_env:
            self._load_env_file()
    
    def _load_env_file(self) -> None:
        """Load .env file from current working directory."""
        env_file = Path.cwd() / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=False)
    
    
    def create_default_config(self) -> CaseCraftConfig:
        """Create default configuration from environment variables."""
        env_overrides = self.get_env_overrides()
        config_dict = {}
        
        # Apply environment overrides to default structure
        self._apply_overrides(config_dict, env_overrides)
        
        # Ensure minimum structure exists
        if 'llm' not in config_dict:
            config_dict['llm'] = {}
        if 'output' not in config_dict:
            config_dict['output'] = {}
        if 'processing' not in config_dict:
            config_dict['processing'] = {}
            
        return CaseCraftConfig(**config_dict)
    
    
    
    def load_config_with_overrides(
        self,
        env_overrides: Optional[Dict[str, Any]] = None,
        cli_overrides: Optional[Dict[str, Any]] = None
    ) -> CaseCraftConfig:
        """Load configuration from environment variables and CLI overrides.
        
        Priority: CLI args > Environment variables > Defaults
        
        Args:
            env_overrides: Environment variable overrides
            cli_overrides: Command line argument overrides
            
        Returns:
            Configuration with overrides applied
        """
        # Start with default config from environment
        config = self.create_default_config()
        config_dict = config.dict()
        
        # Apply environment overrides
        if env_overrides is None:
            env_overrides = self.get_env_overrides()
        if env_overrides:
            self._apply_overrides(config_dict, env_overrides)
        
        # Apply CLI overrides (highest priority)
        if cli_overrides:
            self._apply_overrides(config_dict, cli_overrides)
        
        return CaseCraftConfig(**config_dict)
    
    def _apply_overrides(self, config_dict: Dict[str, Any], overrides: Dict[str, Any]) -> None:
        """Apply overrides to configuration dictionary.
        
        Args:
            config_dict: Configuration dictionary to modify
            overrides: Override values to apply
        """
        for key, value in overrides.items():
            if value is not None:
                # Handle nested keys like "llm.api_key"
                keys = key.split('.')
                current = config_dict
                
                for k in keys[:-1]:
                    current = current.setdefault(k, {})
                
                current[keys[-1]] = value
    
    def get_env_overrides(self) -> Dict[str, Any]:
        """Extract configuration overrides from environment variables.
        
        Environment variables should be prefixed with CASECRAFT_
        Examples:
            CASECRAFT_LLM_API_KEY -> llm.api_key
            CASECRAFT_OUTPUT_DIRECTORY -> output.directory
            
        Also supports BigModel-specific API key:
            BIGMODEL_API_KEY -> llm.api_key
            
        Returns:
            Dictionary of environment overrides
        """
        overrides = {}
        prefix = "CASECRAFT_"
        
        # Check for BigModel API key environment variable
        bigmodel_api_key = os.getenv("BIGMODEL_API_KEY")
        if bigmodel_api_key:
            overrides["llm.api_key"] = bigmodel_api_key
        
        # Environment variable to config key mapping
        env_mappings = {
            'CASECRAFT_LLM_MODEL': 'llm.model',
            'CASECRAFT_LLM_API_KEY': 'llm.api_key',
            'CASECRAFT_LLM_BASE_URL': 'llm.base_url',
            'CASECRAFT_LLM_TIMEOUT': 'llm.timeout',
            'CASECRAFT_LLM_MAX_RETRIES': 'llm.max_retries',
            'CASECRAFT_LLM_TEMPERATURE': 'llm.temperature',
            'CASECRAFT_LLM_THINK': 'llm.think',
            'CASECRAFT_LLM_STREAM': 'llm.stream',
            'CASECRAFT_OUTPUT_DIRECTORY': 'output.directory',
            'CASECRAFT_OUTPUT_ORGANIZE_BY_TAG': 'output.organize_by_tag',
            'CASECRAFT_OUTPUT_FILENAME_TEMPLATE': 'output.filename_template',
            'CASECRAFT_PROCESSING_WORKERS': 'processing.workers',
            'CASECRAFT_PROCESSING_INCLUDE_TAGS': 'processing.include_tags',
            'CASECRAFT_PROCESSING_EXCLUDE_TAGS': 'processing.exclude_tags',
            'CASECRAFT_PROCESSING_INCLUDE_PATHS': 'processing.include_paths',
            'CASECRAFT_PROCESSING_EXCLUDE_PATHS': 'processing.exclude_paths',
            'CASECRAFT_PROCESSING_FORCE_REGENERATE': 'processing.force_regenerate',
            'CASECRAFT_PROCESSING_DRY_RUN': 'processing.dry_run',
        }
        
        for env_key, config_key in env_mappings.items():
            value = os.getenv(env_key)
            if value is not None:
                # Handle boolean values
                if value.lower() in ('true', 'false'):
                    value = value.lower() == 'true'
                # Handle integer values
                elif value.isdigit():
                    value = int(value)
                # Handle float values
                elif '.' in value and value.replace('.', '').isdigit():
                    value = float(value)
                
                overrides[config_key] = value
        
        return overrides
    
    
    def get_provider_config(self, provider_name: str, workers: Optional[int] = None) -> Dict[str, Any]:
        """Get configuration for a specific provider.
        
        Args:
            provider_name: Provider name (glm, kimi, qwen, etc.)
            workers: Number of workers from CLI (required)
            
        Returns:
            Provider configuration dictionary
            
        Raises:
            ConfigError: If required configuration is missing
        """
        if workers is None:
            raise ConfigError("Workers must be specified via --workers CLI argument")
            
        provider_upper = provider_name.upper()
        
        # Read provider-specific configuration
        config = {
            'name': provider_name,
            'model': os.getenv(f"CASECRAFT_{provider_upper}_MODEL"),
            'api_key': os.getenv(f"CASECRAFT_{provider_upper}_API_KEY"),
            'base_url': os.getenv(f"CASECRAFT_{provider_upper}_BASE_URL"),
            
            # Common configuration with fallbacks
            'timeout': int(os.getenv(f"CASECRAFT_{provider_upper}_TIMEOUT", 
                                     os.getenv("CASECRAFT_LLM_TIMEOUT", "120"))),
            'max_retries': int(os.getenv(f"CASECRAFT_{provider_upper}_MAX_RETRIES",
                                         os.getenv("CASECRAFT_LLM_MAX_RETRIES", "3"))),
            'temperature': float(os.getenv(f"CASECRAFT_{provider_upper}_TEMPERATURE",
                                           os.getenv("CASECRAFT_LLM_TEMPERATURE", "0.7"))),
            'stream': os.getenv(f"CASECRAFT_{provider_upper}_STREAM",
                               os.getenv("CASECRAFT_LLM_STREAM", "true")).lower() == "true",
            'workers': workers  # Use CLI value directly
        }
        
        # Validate required configuration
        if not config['api_key']:
            raise ConfigError(
                f"API key not configured for {provider_name}. "
                f"Please set CASECRAFT_{provider_upper}_API_KEY in .env file"
            )
        
        if not config['model']:
            raise ConfigError(
                f"Model not configured for {provider_name}. "
                f"Please set CASECRAFT_{provider_upper}_MODEL in .env file"
            )
        
        return config
    
    def validate_config(self, config: CaseCraftConfig) -> None:
        """Validate configuration completeness.
        
        Args:
            config: Configuration to validate
            
        Raises:
            ConfigError: If configuration is invalid or incomplete
        """
        # Check for required model configuration
        if not config.llm.model:
            raise ConfigError(
                "Model not configured. Please set CASECRAFT_LLM_MODEL environment variable "
                "or add it to your .env file. Example: CASECRAFT_LLM_MODEL=glm-4.5"
            )
        
        # Check for required API key
        if not config.llm.api_key:
            raise ConfigError(
                "API key not configured. Please set CASECRAFT_LLM_API_KEY or BIGMODEL_API_KEY environment variable, "
                "or create a .env file with the API key."
            )
        
        # Validate output directory is writable
        output_path = Path(config.output.directory)
        if output_path.exists() and not os.access(output_path, os.W_OK):
            raise ConfigError(f"Output directory is not writable: {output_path}")
        
        # Validate worker count for BigModel
        if config.processing.workers != 1:
            raise ConfigError("BigModel only supports single concurrency. Please set CASECRAFT_PROCESSING_WORKERS=1")