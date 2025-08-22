"""Module analyzer for intelligent module detection."""

import re
from typing import Optional

from casecraft.config.template_manager import TemplateManager
from casecraft.models.api_spec import APIEndpoint


class ModuleAnalyzer:
    """Analyzes API endpoints to determine their module categorization."""
    
    def __init__(self, template_manager: Optional[TemplateManager] = None):
        """Initialize the module analyzer.
        
        Args:
            template_manager: Template configuration manager
        """
        self.template_manager = template_manager or TemplateManager()
        self.patterns = self.template_manager.get_module_patterns()
        self.default_module = self.template_manager.get_default_module()
    
    def analyze(self, endpoint: APIEndpoint) -> str:
        """Analyze endpoint and return module name.
        
        Args:
            endpoint: API endpoint to analyze
            
        Returns:
            Module name
        """
        # If no patterns configured (zero-config mode), use default extraction
        if not self.patterns:
            return self._get_default_module(endpoint)
        
        path_lower = endpoint.path.lower()
        
        # Check each pattern configuration
        for pattern_config in self.patterns:
            pattern = pattern_config.get('regex', '')
            if pattern and re.search(pattern, path_lower):
                return pattern_config.get('name', self.default_module)
        
        # Fall back to default module extraction
        return self._get_default_module(endpoint)
    
    def get_module_prefix(self, module: str) -> str:
        """Get module prefix for case ID generation.
        
        Args:
            module: Module name
            
        Returns:
            Module prefix (e.g., 'USR' for '用户管理')
        """
        # If patterns exist, check if module has a configured prefix
        if self.patterns:
            for pattern_config in self.patterns:
                if pattern_config.get('name') == module:
                    return pattern_config.get('prefix', self._generate_prefix(module))
        
        # Zero-config mode or no match: generate prefix
        return self._generate_prefix(module)
    
    def _get_default_module(self, endpoint: APIEndpoint) -> str:
        """Extract default module name from path.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            Default module name
        """
        # Extract from path segments
        parts = endpoint.path.strip('/').split('/')
        
        # Skip 'api' and version parts
        for i, part in enumerate(parts):
            if part.lower() in ['api', 'v1', 'v2', 'v3']:
                continue
            # Return the first meaningful segment
            if part:
                # Remove trailing 's' for plural and capitalize
                module_name = part.rstrip('s').replace('_', ' ').replace('-', ' ')
                return module_name.title() + '管理'
        
        return self.default_module
    
    def _generate_prefix(self, module: str) -> str:
        """Generate a prefix from module name.
        
        Args:
            module: Module name
            
        Returns:
            Generated prefix (first 3 uppercase letters)
        """
        # Remove common Chinese suffixes
        clean_name = module.replace('管理', '').replace('系统', '')
        
        # Take first 3 characters and uppercase
        if clean_name:
            # Handle Chinese characters by using pinyin-like abbreviations
            if any('\u4e00' <= char <= '\u9fff' for char in clean_name):
                # Simple mapping for common Chinese modules
                chinese_mapping = {
                    '用户': 'USR',
                    '认证': 'AUTH',
                    '授权': 'AUTH',
                    '订单': 'ORD',
                    '商品': 'PRD',
                    '购物车': 'CART',
                    '支付': 'PAY',
                    '分类': 'CAT',
                    '后台': 'ADM',
                    '通用': 'GEN'
                }
                for chinese, prefix in chinese_mapping.items():
                    if chinese in clean_name:
                        return prefix
            
            # For English, take first 3 letters
            english_only = ''.join(c for c in clean_name if c.isalnum())
            if english_only:
                return english_only[:3].upper()
        
        return 'GEN'  # Generic prefix