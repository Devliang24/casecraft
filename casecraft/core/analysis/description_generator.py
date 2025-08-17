"""
智能描述生成器
根据OpenAPI信息和路径分析生成中文描述
"""

from typing import Optional
from .path_analyzer import PathAnalyzer
from .constants import RESOURCE_TRANSLATIONS, OPERATION_VERBS


class SmartDescriptionGenerator:
    """智能端点描述生成器"""
    
    def __init__(self):
        """初始化描述生成器"""
        self.path_analyzer = PathAnalyzer()
        
    def generate(self, endpoint) -> str:
        """
        生成端点的中文描述
        
        Args:
            endpoint: APIEndpoint对象
            
        Returns:
            中文描述字符串
        """
        # 1. 优先使用OpenAPI提供的summary
        if hasattr(endpoint, 'summary') and endpoint.summary:
            summary = endpoint.summary.strip()
            if summary and len(summary) <= 20:
                return summary
            # 如果太长，尝试提取关键部分
            if summary:
                # 取第一句或前20个字符
                first_sentence = summary.split('.')[0].split('。')[0]
                if len(first_sentence) <= 20:
                    return first_sentence
                else:
                    return summary[:20].rsplit(' ', 1)[0] + "..."
        
        # 2. 尝试从description提取
        if hasattr(endpoint, 'description') and endpoint.description:
            description = endpoint.description.strip()
            if description:
                # 取第一行
                first_line = description.split('\n')[0].strip()
                if first_line and len(first_line) <= 20:
                    return first_line
        
        # 3. 智能推断生成
        return self._generate_from_analysis(endpoint)
    
    def _generate_from_analysis(self, endpoint) -> str:
        """
        基于路径分析生成描述
        
        Args:
            endpoint: APIEndpoint对象
            
        Returns:
            生成的中文描述
        """
        # 分析路径
        analysis = self.path_analyzer.analyze(endpoint.path, endpoint.method)
        
        # 获取主要资源
        primary_resource = analysis.get('primary_resource')
        operation_type = analysis.get('operation_type')
        is_collection = analysis.get('is_collection', False)
        
        # 翻译资源名
        resource_cn = self._translate_resource(primary_resource)
        
        # 生成操作描述
        verb = self._get_operation_verb(endpoint.method.upper(), operation_type, is_collection)
        
        # 组合描述
        if operation_type == 'collection' and endpoint.method.upper() == 'GET':
            return f"{verb}{resource_cn}列表"
        elif operation_type == 'single' and endpoint.method.upper() == 'GET':
            return f"{verb}{resource_cn}详情"
        elif operation_type == 'create':
            return f"{verb}{resource_cn}"
        elif operation_type == 'update':
            return f"{verb}{resource_cn}"
        elif operation_type == 'single' and endpoint.method.upper() == 'DELETE':
            return f"{verb}{resource_cn}"
        elif operation_type == 'collection' and endpoint.method.upper() == 'DELETE':
            return f"{verb}{resource_cn}"
        else:
            return f"{verb}{resource_cn}"
    
    def _translate_resource(self, resource: Optional[str]) -> str:
        """
        翻译资源名为中文
        
        Args:
            resource: 英文资源名
            
        Returns:
            中文资源名
        """
        if not resource:
            return "资源"
        
        # 从常量中查找翻译
        translated = RESOURCE_TRANSLATIONS.get(resource.lower())
        if translated:
            return translated
        
        # 如果没有找到翻译，返回原文
        return resource
    
    def _get_operation_verb(self, method: str, operation_type: str, is_collection: bool) -> str:
        """
        获取操作动词
        
        Args:
            method: HTTP方法
            operation_type: 操作类型
            is_collection: 是否为集合操作
            
        Returns:
            操作动词
        """
        # 从常量中获取动词映射
        method_verbs = OPERATION_VERBS.get(method, {})
        
        if method == 'GET':
            if operation_type == 'collection' or is_collection:
                return method_verbs.get('collection', '获取')
            else:
                return method_verbs.get('single', '获取')
        elif method == 'POST':
            return method_verbs.get('collection', '创建')
        elif method in ['PUT', 'PATCH']:
            if operation_type == 'collection' or is_collection:
                return method_verbs.get('collection', '批量更新')
            else:
                return method_verbs.get('single', '更新' if method == 'PUT' else '修改')
        elif method == 'DELETE':
            if operation_type == 'collection' or is_collection:
                return method_verbs.get('collection', '清空')
            else:
                return method_verbs.get('single', '删除')
        else:
            return '操作'
    
    def generate_detailed_description(self, endpoint) -> str:
        """
        生成详细描述（用于提示词等场景）
        
        Args:
            endpoint: APIEndpoint对象
            
        Returns:
            详细的中文描述
        """
        # 基础描述
        basic_desc = self.generate(endpoint)
        
        # 分析路径获取更多信息
        analysis = self.path_analyzer.analyze(endpoint.path, endpoint.method)
        
        # 添加路径信息
        path_info = f"路径: {endpoint.path}"
        method_info = f"方法: {endpoint.method.upper()}"
        
        # 添加特征信息
        features = []
        if analysis.get('has_path_params'):
            features.append("包含路径参数")
        if analysis.get('is_nested'):
            features.append("嵌套资源操作")
        if analysis.get('is_collection'):
            features.append("集合操作")
        
        # 组合详细描述
        parts = [basic_desc, path_info, method_info]
        if features:
            parts.append(f"特征: {', '.join(features)}")
        
        return " | ".join(parts)
    
    def generate_test_scenario_hint(self, endpoint) -> str:
        """
        生成测试场景提示
        
        Args:
            endpoint: APIEndpoint对象
            
        Returns:
            测试场景提示文本
        """
        analysis = self.path_analyzer.analyze(endpoint.path, endpoint.method)
        method = endpoint.method.upper()
        
        hints = []
        
        # 基于HTTP方法的通用提示
        if method == 'GET':
            if analysis.get('is_collection'):
                hints.append("测试分页、排序、过滤参数")
            else:
                hints.append("测试资源存在/不存在场景")
        elif method == 'POST':
            hints.append("测试必填字段、数据格式验证、重复创建")
        elif method in ['PUT', 'PATCH']:
            hints.append("测试字段更新、部分更新、并发冲突")
        elif method == 'DELETE':
            hints.append("测试删除确认、级联删除、权限检查")
        
        # 基于路径特征的提示
        if analysis.get('has_path_params'):
            hints.append("测试无效ID、权限验证")
        
        # 基于资源类型的提示
        primary_resource = analysis.get('primary_resource', '').lower()
        if any(keyword in primary_resource for keyword in ['auth', 'login', 'token']):
            hints.append("测试认证失败、令牌过期")
        elif any(keyword in primary_resource for keyword in ['pay', 'order', 'transaction']):
            hints.append("测试金额验证、状态转换")
        
        return "; ".join(hints) if hints else "测试基本功能和异常情况"