"""Postcondition generator for test cases."""

from typing import List, Optional

from casecraft.config.template_manager import TemplateManager
from casecraft.models.api_spec import APIEndpoint


class PostconditionGenerator:
    """Generates postconditions/cleanup steps for test cases."""
    
    def __init__(self, template_manager: Optional[TemplateManager] = None):
        """Initialize the postcondition generator.
        
        Args:
            template_manager: Template configuration manager
        """
        self.template_manager = template_manager or TemplateManager()
        self.templates = self.template_manager.get_postcondition_templates()
        self.cleanup_required_methods = ["POST", "PUT", "PATCH", "DELETE"]
    
    def generate(self, endpoint: APIEndpoint, test_type: str) -> List[str]:
        """Generate postconditions for an endpoint.
        
        Args:
            endpoint: API endpoint
            test_type: Type of test (positive/negative/boundary)
            
        Returns:
            List of postcondition strings
        """
        # Negative and boundary tests typically don't need cleanup
        if test_type in ["negative", "boundary"]:
            return []
        
        method = endpoint.method.upper()
        
        # GET and HEAD requests don't modify state
        if method not in self.cleanup_required_methods:
            return []
        
        # Generate based on method
        if method == "POST":
            return self._generate_post_cleanup(endpoint)
        elif method in ["PUT", "PATCH"]:
            return self._generate_update_cleanup(endpoint)
        elif method == "DELETE":
            return self._generate_delete_cleanup(endpoint)
        
        return []
    
    def _generate_post_cleanup(self, endpoint: APIEndpoint) -> List[str]:
        """Generate cleanup steps for POST operations.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            List of cleanup steps
        """
        cleanups = []
        path_lower = endpoint.path.lower()
        
        # Check for specific resource types
        if 'order' in path_lower:
            cleanups.append(self.templates.get('delete_order', "删除测试创建的订单"))
            cleanups.append(self.templates.get('restore_stock', "恢复商品库存"))
        elif 'user' in path_lower or 'register' in path_lower:
            cleanups.append(self.templates.get('delete_user', "删除测试创建的用户账号"))
        elif 'product' in path_lower:
            cleanups.append(self.templates.get('delete_product', "删除测试创建的商品"))
        elif 'cart' in path_lower:
            cleanups.append(self.templates.get('clear_cart', "清空测试购物车"))
        elif 'payment' in path_lower:
            cleanups.append("撤销测试支付记录")
        elif 'category' in path_lower or 'categories' in path_lower:
            cleanups.append("删除测试创建的分类")
        else:
            # Generic cleanup for unknown resources
            cleanups.append(self.templates.get('delete_generic', "删除测试创建的数据"))
        
        return cleanups
    
    def _generate_update_cleanup(self, endpoint: APIEndpoint) -> List[str]:
        """Generate cleanup steps for PUT/PATCH operations.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            List of cleanup steps
        """
        cleanups = []
        path_lower = endpoint.path.lower()
        
        # Check for specific update scenarios
        if 'password' in path_lower:
            cleanups.append(self.templates.get('restore_password', "恢复原始密码"))
        elif 'profile' in path_lower or 'user' in path_lower:
            cleanups.append(self.templates.get('restore_profile', "恢复用户原始信息"))
        elif 'status' in path_lower:
            cleanups.append(self.templates.get('restore_status', "恢复原始状态"))
        elif 'setting' in path_lower or 'config' in path_lower:
            cleanups.append("恢复原始配置")
        elif 'stock' in path_lower or 'inventory' in path_lower:
            cleanups.append("恢复原始库存数量")
        else:
            # Generic restoration
            cleanups.append(self.templates.get('restore_generic', "恢复资源原始数据"))
        
        return cleanups
    
    def _generate_delete_cleanup(self, endpoint: APIEndpoint) -> List[str]:
        """Generate verification steps for DELETE operations.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            List of verification steps
        """
        # For DELETE operations, we verify rather than clean up
        return [
            self.templates.get('verify_deleted', "验证资源已被正确删除"),
            self.templates.get('verify_related', "确认相关联数据已处理")
        ]