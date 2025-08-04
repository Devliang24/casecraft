"""Configuration management for CaseCraft."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import ValidationError

from casecraft.models.config import CaseCraftConfig


class ConfigError(Exception):
    """Configuration related errors."""
    pass


class ConfigManager:
    """Manages CaseCraft configuration loading and saving."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration manager.
        
        Args:
            config_path: Optional custom path to config file.
                        Defaults to ~/.casecraft/config.yaml
        """
        self.config_path = config_path or CaseCraftConfig.get_config_path()
        self.config_dir = self.config_path.parent
    
    def ensure_config_dir(self) -> None:
        """Ensure configuration directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Set restrictive permissions on config directory
        if os.name != 'nt':  # Not Windows
            os.chmod(self.config_dir, 0o700)
    
    def create_default_config(self) -> CaseCraftConfig:
        """Create default configuration with placeholders."""
        return CaseCraftConfig()
    
    def save_config(self, config: CaseCraftConfig) -> None:
        """Save configuration to file.
        
        Args:
            config: Configuration object to save
            
        Raises:
            ConfigError: If unable to save configuration
        """
        try:
            self.ensure_config_dir()
            
            # Convert to dict and remove sensitive defaults
            config_dict = config.dict()
            
            # Don't save empty/default API key
            if config_dict.get("llm", {}).get("api_key") is None:
                config_dict.setdefault("llm", {})["api_key"] = "<YOUR_API_KEY_HERE>"
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_dict, f, default_flow_style=False, indent=2)
            
            # Set restrictive permissions on config file
            if os.name != 'nt':  # Not Windows
                os.chmod(self.config_path, 0o600)
                
        except (OSError, yaml.YAMLError) as e:
            raise ConfigError(f"Failed to save configuration: {e}") from e
    
    def load_config(self) -> CaseCraftConfig:
        """Load configuration from file.
        
        Returns:
            Loaded configuration object
            
        Raises:
            ConfigError: If unable to load or parse configuration
        """
        if not self.config_path.exists():
            raise ConfigError(f"Configuration file not found: {self.config_path}")
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f) or {}
            
            return CaseCraftConfig(**config_data)
            
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in configuration file: {e}") from e
        except ValidationError as e:
            raise ConfigError(f"Invalid configuration: {e}") from e
        except OSError as e:
            raise ConfigError(f"Failed to read configuration file: {e}") from e
    
    def load_config_with_overrides(
        self,
        env_overrides: Optional[Dict[str, Any]] = None,
        cli_overrides: Optional[Dict[str, Any]] = None
    ) -> CaseCraftConfig:
        """Load configuration with environment and CLI overrides.
        
        Priority: CLI args > Environment variables > Config file > Defaults
        
        Args:
            env_overrides: Environment variable overrides
            cli_overrides: Command line argument overrides
            
        Returns:
            Configuration with overrides applied
        """
        # Start with file config or defaults
        try:
            config = self.load_config()
        except ConfigError:
            config = self.create_default_config()
        
        config_dict = config.dict()
        
        # Apply environment overrides
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
        
        for key, value in os.environ.items():
            if key.startswith(prefix):
                # Convert CASECRAFT_LLM_API_KEY to llm.api_key
                config_key = key[len(prefix):].lower().replace('_', '.')
                
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
    
    def config_exists(self) -> bool:
        """Check if configuration file exists."""
        return self.config_path.exists()
    
    def validate_config(self, config: CaseCraftConfig) -> None:
        """Validate configuration completeness.
        
        Args:
            config: Configuration to validate
            
        Raises:
            ConfigError: If configuration is invalid or incomplete
        """
        # Check for required API key
        if not config.llm.api_key or config.llm.api_key == "<YOUR_API_KEY_HERE>":
            raise ConfigError(
                "API key not configured. Please set your BigModel API key in the configuration file "
                f"({self.config_path}) or via environment variable BIGMODEL_API_KEY"
            )
        
        # Validate output directory is writable
        output_path = Path(config.output.directory)
        if output_path.exists() and not os.access(output_path, os.W_OK):
            raise ConfigError(f"Output directory is not writable: {output_path}")
        
        # Validate worker count for BigModel
        if config.processing.workers != 1:
            raise ConfigError("BigModel only supports single concurrency. Please set workers to 1")