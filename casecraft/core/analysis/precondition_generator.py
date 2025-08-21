"""Precondition generator for test cases."""

import re
from typing import List, Optional

from casecraft.config.template_manager import TemplateManager
from casecraft.models.api_spec import APIEndpoint


class PreconditionGenerator:
    """Generates preconditions for test cases based on endpoint characteristics."""
    
    def __init__(self, template_manager: Optional[TemplateManager] = None):
        """Initialize the precondition generator.
        
        Args:
            template_manager: Template configuration manager
        """
        self.template_manager = template_manager or TemplateManager()
        self.templates = self.template_manager.get_precondition_templates()
        self.auth_patterns = ['auth', 'token', 'key', 'bearer', 'credential', 'jwt', 'oauth']
    
    def generate(self, endpoint: APIEndpoint, test_type: Optional[str] = None) -> List[str]:
        """Generate preconditions for an endpoint.
        
        Args:
            endpoint: API endpoint
            test_type: Type of test (positive/negative/boundary)
            
        Returns:
            List of precondition strings
        """
        preconditions = []
        
        # Check authentication requirements
        auth_conditions = self._check_authentication(endpoint)
        preconditions.extend(auth_conditions)
        
        # Check data dependencies
        data_conditions = self._check_data_dependencies(endpoint)
        preconditions.extend(data_conditions)
        
        # Check method-specific conditions
        method_conditions = self._check_method_specific(endpoint)
        preconditions.extend(method_conditions)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_conditions = []
        for condition in preconditions:
            if condition not in seen:
                seen.add(condition)
                unique_conditions.append(condition)
        
        return unique_conditions
    
    def _check_authentication(self, endpoint: APIEndpoint) -> List[str]:
        """Check authentication-related preconditions.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            List of authentication preconditions
        """
        conditions = []
        
        # Check if endpoint has security requirements
        if hasattr(endpoint, 'security') and endpoint.security:
            # Determine the type of authentication
            for security_scheme in endpoint.security:
                if isinstance(security_scheme, dict):
                    for scheme_name in security_scheme.keys():
                        if 'bearer' in scheme_name.lower() or 'jwt' in scheme_name.lower():
                            conditions.append(self.templates.get('auth_token', 
                                "用户已登录并获取有效的Bearer Token"))
                        elif 'apikey' in scheme_name.lower() or 'api_key' in scheme_name.lower():
                            conditions.append(self.templates.get('api_key', 
                                "已配置有效的API Key"))
        
        # Check parameters for authentication requirements
        if endpoint.parameters:
            for param in endpoint.parameters:
                param_name = getattr(param, 'name', param.get('name', '')).lower()
                
                # Check if parameter name indicates authentication
                if any(pattern in param_name for pattern in self.auth_patterns):
                    if param_name in ['authorization', 'auth-token', 'bearer-token']:
                        if self.templates.get('auth_token') not in conditions:
                            conditions.append(self.templates.get('auth_token', 
                                "用户已登录并获取有效的Bearer Token"))
                    elif 'api' in param_name and 'key' in param_name:
                        if self.templates.get('api_key') not in conditions:
                            conditions.append(self.templates.get('api_key', 
                                "已配置有效的API Key"))
        
        return conditions
    
    def _check_data_dependencies(self, endpoint: APIEndpoint) -> List[str]:
        """Check data dependency preconditions.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            List of data dependency preconditions
        """
        conditions = []
        
        # Check for path parameters that indicate resource dependencies
        if '{' in endpoint.path:
            # Extract parameter names from path
            params = re.findall(r'\{(\w+)\}', endpoint.path)
            for param in params:
                if 'id' in param.lower():
                    # Extract resource name from path
                    resource = self._extract_resource_name(endpoint.path, param)
                    template = self.templates.get('resource_exists', 
                        "数据库中存在测试{resource}")
                    conditions.append(template.format(resource=resource))
                elif 'code' in param.lower():
                    conditions.append(f"存在有效的{param}")
        
        # Check for specific path patterns
        path_lower = endpoint.path.lower()
        if '/cart' in path_lower and endpoint.method.upper() == 'POST':
            conditions.append(self.templates.get('cart_has_items', "购物车中有商品"))
        
        if '/order' in path_lower and endpoint.method.upper() == 'POST':
            conditions.append(self.templates.get('stock_sufficient', "商品库存充足"))
        
        return conditions
    
    def _check_method_specific(self, endpoint: APIEndpoint) -> List[str]:
        """Check HTTP method-specific preconditions.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            List of method-specific preconditions
        """
        conditions = []
        method = endpoint.method.upper()
        
        if method in ['PUT', 'PATCH']:
            conditions.append(self.templates.get('resource_updatable', 
                "待更新的资源存在且状态正常"))
        elif method == 'DELETE':
            conditions.append(self.templates.get('resource_deletable', 
                "待删除的资源存在且无关联依赖"))
        
        return conditions
    
    def _extract_resource_name(self, path: str, param: str) -> str:
        """Extract resource name from API path.
        
        Args:
            path: API path
            param: Parameter name
            
        Returns:
            Resource name
        """
        # Split path and look for the segment before the parameter
        parts = path.split('/')
        for i, part in enumerate(parts):
            if '{' + param + '}' in part and i > 0:
                # Get the previous segment as resource name
                resource = parts[i-1].rstrip('s')  # Remove plural 's'
                
                # Translate common English resources to Chinese
                resource_mapping = {
                    'user': '用户',
                    'order': '订单',
                    'product': '商品',
                    'category': '分类',
                    'cart': '购物车项',
                    'payment': '支付记录',
                    'item': '项目'
                }
                
                return resource_mapping.get(resource, resource)
        
        return "资源"