"""Template configuration manager for CaseCraft."""

import yaml
from pathlib import Path
from typing import Any, Dict, Optional


class TemplateManager:
    """Manages template configurations for test case generation.
    
    Loads configuration from either a custom file specified via --config
    or falls back to the default configuration.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the template manager.
        
        Args:
            config_path: Optional path to custom configuration file
        """
        self.config = self._load_config(config_path)
    
    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from file.
        
        Priority: Custom config (if provided) > Default config
        
        Args:
            config_path: Optional path to custom configuration file
            
        Returns:
            Configuration dictionary
        """
        # Try custom config first
        if config_path:
            config_file = Path(config_path)
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            else:
                raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        # Fall back to default config
        # Try project root first
        default_config = Path.cwd() / 'default_templates.yaml'
        if not default_config.exists():
            # Try package directory as fallback (for pip installed version)
            default_config = Path(__file__).parent / 'default_templates.yaml'
            if not default_config.exists():
                raise FileNotFoundError(f"Default configuration not found in project root or package")
        
        with open(default_config, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def get_module_patterns(self) -> list:
        """Get module mapping patterns.
        
        Returns:
            List of module pattern configurations
        """
        return self.config.get('modules', {}).get('patterns', [])
    
    def get_default_module(self) -> str:
        """Get default module name.
        
        Returns:
            Default module name
        """
        return self.config.get('modules', {}).get('default', '通用接口')
    
    def get_priority_rules(self) -> list:
        """Get priority determination rules.
        
        Returns:
            List of priority rules
        """
        return self.config.get('priorities', {}).get('rules', [])
    
    def get_default_priority(self) -> str:
        """Get default priority.
        
        Returns:
            Default priority level
        """
        return self.config.get('priorities', {}).get('default', 'P2')
    
    def get_precondition_templates(self) -> Dict[str, str]:
        """Get precondition text templates.
        
        Returns:
            Dictionary of precondition templates
        """
        return self.config.get('templates', {}).get('preconditions', {})
    
    def get_postcondition_templates(self) -> Dict[str, str]:
        """Get postcondition text templates.
        
        Returns:
            Dictionary of postcondition templates
        """
        return self.config.get('templates', {}).get('postconditions', {})
    
    def get_excel_columns(self) -> list:
        """Get Excel column definitions.
        
        Returns:
            List of column configurations
        """
        return self.config.get('excel', {}).get('columns', [])
    
    def get_excel_styles(self) -> Dict[str, Any]:
        """Get Excel style definitions.
        
        Returns:
            Dictionary of style configurations
        """
        return self.config.get('excel', {}).get('styles', {})