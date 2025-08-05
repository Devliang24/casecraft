"""Tests for configuration management."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from casecraft.core.management.config_manager import ConfigManager, ConfigError
from casecraft.models.config import CaseCraftConfig, LLMConfig


class TestConfigManager:
    """Test configuration manager functionality."""
    
    def test_init_default_path(self):
        """Test initialization with default path."""
        manager = ConfigManager()
        expected_path = Path.home() / ".casecraft" / "config.yaml"
        assert manager.config_path == expected_path
    
    def test_init_custom_path(self, tmp_path):
        """Test initialization with custom path."""
        custom_path = tmp_path / "custom_config.yaml"
        manager = ConfigManager(custom_path)
        assert manager.config_path == custom_path
    
    def test_ensure_config_dir(self, tmp_path):
        """Test configuration directory creation."""
        config_path = tmp_path / "config" / "config.yaml"
        manager = ConfigManager(config_path)
        
        assert not manager.config_dir.exists()
        manager.ensure_config_dir()
        assert manager.config_dir.exists()
        assert manager.config_dir.is_dir()
    
    def test_create_default_config(self):
        """Test default configuration creation."""
        manager = ConfigManager()
        config = manager.create_default_config()
        
        assert isinstance(config, CaseCraftConfig)
        assert config.llm.model == "glm-4.5-x"
        assert config.output.directory == "test_cases"
        assert config.processing.workers == 4
    
    def test_save_and_load_config(self, tmp_path):
        """Test configuration save and load cycle."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path)
        
        # Create test config
        config = CaseCraftConfig(
            llm=LLMConfig(
                model="glm-4.5-x",
                api_key="test-key-123"
            )
        )
        
        # Save config
        manager.save_config(config)
        assert config_path.exists()
        
        # Load config
        loaded_config = manager.load_config()
        assert loaded_config.llm.model == "glm-4.5-x"
        assert loaded_config.llm.api_key == "test-key-123"
    
    def test_save_config_with_placeholder_api_key(self, tmp_path):
        """Test saving config with placeholder for empty API key."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path)
        
        config = CaseCraftConfig()  # Default config with no API key
        manager.save_config(config)
        
        # Check file content
        with open(config_path) as f:
            saved_data = yaml.safe_load(f)
        
        assert saved_data["llm"]["api_key"] == "<YOUR_API_KEY_HERE>"
    
    def test_load_nonexistent_config(self, tmp_path):
        """Test loading non-existent configuration."""
        config_path = tmp_path / "nonexistent.yaml"
        manager = ConfigManager(config_path)
        
        with pytest.raises(ConfigError, match="Configuration file not found"):
            manager.load_config()
    
    def test_load_invalid_yaml(self, tmp_path):
        """Test loading invalid YAML configuration."""
        config_path = tmp_path / "invalid.yaml"
        manager = ConfigManager(config_path)
        
        # Write invalid YAML
        config_path.write_text("invalid: yaml: content: [")
        
        with pytest.raises(ConfigError, match="Invalid YAML"):
            manager.load_config()
    
    def test_get_env_overrides(self):
        """Test environment variable override extraction."""
        manager = ConfigManager()
        
        with patch.dict(os.environ, {
            'CASECRAFT_LLM_API_KEY': 'env-key-123',
            'CASECRAFT_OUTPUT_DIRECTORY': 'env_output',
            'CASECRAFT_PROCESSING_WORKERS': '8',
            'CASECRAFT_PROCESSING_DRY_RUN': 'true',
            'OTHER_VAR': 'ignored'
        }):
            overrides = manager.get_env_overrides()
        
        assert overrides == {
            'llm.api_key': 'env-key-123',
            'output.directory': 'env_output',
            'processing.workers': 8,
            'processing.dry_run': True
        }
    
    def test_load_config_with_overrides(self, tmp_path):
        """Test loading configuration with overrides."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path)
        
        # Save base config
        base_config = CaseCraftConfig()
        manager.save_config(base_config)
        
        # Load with overrides
        env_overrides = {'llm.api_key': 'env-key'}
        cli_overrides = {'processing.workers': 16}
        
        config = manager.load_config_with_overrides(env_overrides, cli_overrides)
        
        assert config.llm.api_key == 'env-key'
        assert config.processing.workers == 16
        assert config.llm.model == "glm-4.5-x"  # Default preserved
    
    def test_validate_config_valid(self):
        """Test validation of valid configuration."""
        manager = ConfigManager()
        config = CaseCraftConfig(
            llm=LLMConfig(api_key="valid-key-123")
        )
        
        # Should not raise
        manager.validate_config(config)
    
    def test_validate_config_missing_api_key(self):
        """Test validation with missing API key."""
        manager = ConfigManager()
        config = CaseCraftConfig()  # No API key
        
        with pytest.raises(ConfigError, match="API key not configured"):
            manager.validate_config(config)
    
    def test_validate_config_placeholder_api_key(self):
        """Test validation with placeholder API key."""
        manager = ConfigManager()
        config = CaseCraftConfig(
            llm=LLMConfig(api_key="<YOUR_API_KEY_HERE>")
        )
        
        with pytest.raises(ConfigError, match="API key not configured"):
            manager.validate_config(config)
    
    def test_validate_config_invalid_workers(self):
        """Test validation with invalid worker count."""
        manager = ConfigManager()
        config = CaseCraftConfig(
            llm=LLMConfig(api_key="valid-key")
        )
        config.processing.workers = 0
        
        with pytest.raises(ConfigError, match="Worker count must be at least 1"):
            manager.validate_config(config)
        
        config.processing.workers = 50
        with pytest.raises(ConfigError, match="Worker count should not exceed 32"):
            manager.validate_config(config)
    
    def test_config_exists(self, tmp_path):
        """Test configuration file existence check."""
        config_path = tmp_path / "config.yaml"
        manager = ConfigManager(config_path)
        
        assert not manager.config_exists()
        
        config_path.touch()
        assert manager.config_exists()