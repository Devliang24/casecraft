"""Headers智能分析器模块。

基于API规范自动推断和生成合适的HTTP headers。
"""

from typing import Dict, List, Optional, Any, Set
from enum import Enum

from casecraft.models.api_spec import APIEndpoint, APIParameter


class AuthType(Enum):
    """认证类型枚举。"""
    NONE = "none"
    BEARER_TOKEN = "bearer"
    API_KEY = "apikey"
    BASIC_AUTH = "basic"
    OAUTH2 = "oauth2"


class ContentType(Enum):
    """内容类型枚举。"""
    JSON = "application/json"
    FORM_DATA = "application/x-www-form-urlencoded"
    MULTIPART = "multipart/form-data"
    XML = "application/xml"
    TEXT = "text/plain"


class HeadersAnalyzer:
    """Headers智能分析器。
    
    基于API端点的特征自动推断和生成合适的HTTP headers。
    """
    
    def __init__(self):
        """初始化Headers分析器。"""
        self.default_accept = "application/json"
        
    def analyze_headers(self, endpoint: APIEndpoint, spec_data: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, str]]:
        """分析端点并生成headers建议。
        
        Args:
            endpoint: API端点信息
            spec_data: 完整的API规范数据，用于分析security schemes
            
        Returns:
            包含不同测试场景headers的字典：
            {
                "positive": {"Content-Type": "application/json", ...},
                "negative_auth": {"Accept": "application/json"},  # 缺失认证
                "negative_content_type": {...},  # 错误Content-Type
                "negative_accept": {...}  # 错误Accept
            }
        """
        headers_scenarios = {}
        
        # 分析基础headers
        base_headers = self._get_base_headers(endpoint)
        
        # 分析认证headers
        auth_headers = self._analyze_auth_headers(endpoint, spec_data)
        
        # 生成正向测试headers
        positive_headers = {**base_headers, **auth_headers}
        headers_scenarios["positive"] = positive_headers
        
        # 生成负向测试headers
        negative_scenarios = self._generate_negative_headers(endpoint, positive_headers, spec_data)
        headers_scenarios.update(negative_scenarios)
        
        return headers_scenarios
    
    def _get_base_headers(self, endpoint: APIEndpoint) -> Dict[str, str]:
        """获取基于HTTP方法的基础headers。
        
        Args:
            endpoint: API端点信息
            
        Returns:
            基础headers字典
        """
        headers = {}
        method = endpoint.method.upper()
        
        # 所有请求都应该有Accept header
        headers["Accept"] = self.default_accept
        
        # 根据HTTP方法添加Content-Type
        if method in ["POST", "PUT", "PATCH"]:
            # 检查是否有请求体参数
            has_body = self._has_request_body(endpoint)
            if has_body:
                content_type = self._infer_content_type(endpoint)
                headers["Content-Type"] = content_type.value
        
        return headers
    
    def _has_request_body(self, endpoint: APIEndpoint) -> bool:
        """检查端点是否有请求体。
        
        Args:
            endpoint: API端点信息
            
        Returns:
            是否有请求体
        """
        # 检查是否有body类型的参数
        for param in endpoint.parameters:
            if param.location == "body":
                return True
        
        # POST/PUT/PATCH通常有请求体
        return endpoint.method.upper() in ["POST", "PUT", "PATCH"]
    
    def _infer_content_type(self, endpoint: APIEndpoint) -> ContentType:
        """推断内容类型。
        
        Args:
            endpoint: API端点信息
            
        Returns:
            推断的内容类型
        """
        # 检查参数类型来推断内容类型
        for param in endpoint.parameters:
            if param.location == "body":
                if param.type in ["object", "array"]:
                    return ContentType.JSON
                elif param.type == "file":
                    return ContentType.MULTIPART
        
        # 默认使用JSON
        return ContentType.JSON
    
    def _analyze_auth_headers(self, endpoint: APIEndpoint, spec_data: Optional[Dict[str, Any]]) -> Dict[str, str]:
        """分析认证相关的headers。
        
        Args:
            endpoint: API端点信息
            spec_data: 完整的API规范数据
            
        Returns:
            认证headers字典
        """
        if not spec_data:
            return {}
        
        auth_type = self._detect_auth_type(spec_data)
        
        if auth_type == AuthType.BEARER_TOKEN:
            return {"Authorization": "Bearer <valid-token>"}
        elif auth_type == AuthType.API_KEY:
            return self._get_api_key_headers(spec_data)
        elif auth_type == AuthType.BASIC_AUTH:
            return {"Authorization": "Basic <credentials>"}
        elif auth_type == AuthType.OAUTH2:
            return {"Authorization": "Bearer <oauth-token>"}
        
        return {}
    
    def _detect_auth_type(self, spec_data: Dict[str, Any]) -> AuthType:
        """检测API的认证类型。
        
        Args:
            spec_data: 完整的API规范数据
            
        Returns:
            检测到的认证类型
        """
        # 检查OpenAPI 3.0的security schemes
        if "components" in spec_data and "securitySchemes" in spec_data["components"]:
            schemes = spec_data["components"]["securitySchemes"]
            
            for scheme_name, scheme in schemes.items():
                scheme_type = scheme.get("type", "").lower()
                
                if scheme_type == "http":
                    scheme_scheme = scheme.get("scheme", "").lower()
                    if scheme_scheme == "bearer":
                        return AuthType.BEARER_TOKEN
                    elif scheme_scheme == "basic":
                        return AuthType.BASIC_AUTH
                elif scheme_type == "apikey":
                    return AuthType.API_KEY
                elif scheme_type == "oauth2":
                    return AuthType.OAUTH2
        
        # 检查Swagger 2.0的security definitions
        if "securityDefinitions" in spec_data:
            definitions = spec_data["securityDefinitions"]
            
            for def_name, definition in definitions.items():
                def_type = definition.get("type", "").lower()
                
                if def_type == "oauth2":
                    return AuthType.OAUTH2
                elif def_type == "apikey":
                    return AuthType.API_KEY
                elif def_type == "basic":
                    return AuthType.BASIC_AUTH
        
        return AuthType.NONE
    
    def _get_api_key_headers(self, spec_data: Dict[str, Any]) -> Dict[str, str]:
        """获取API Key相关的headers。
        
        Args:
            spec_data: 完整的API规范数据
            
        Returns:
            API Key headers字典
        """
        # 检查OpenAPI 3.0
        if "components" in spec_data and "securitySchemes" in spec_data["components"]:
            schemes = spec_data["components"]["securitySchemes"]
            
            for scheme_name, scheme in schemes.items():
                if scheme.get("type") == "apiKey" and scheme.get("in") == "header":
                    header_name = scheme.get("name", "X-API-Key")
                    return {header_name: "<valid-api-key>"}
        
        # 检查Swagger 2.0
        if "securityDefinitions" in spec_data:
            definitions = spec_data["securityDefinitions"]
            
            for def_name, definition in definitions.items():
                if definition.get("type") == "apiKey" and definition.get("in") == "header":
                    header_name = definition.get("name", "X-API-Key")
                    return {header_name: "<valid-api-key>"}
        
        # 默认API Key header
        return {"X-API-Key": "<valid-api-key>"}
    
    def _generate_negative_headers(self, endpoint: APIEndpoint, positive_headers: Dict[str, str], spec_data: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
        """生成负向测试的headers场景。
        
        Args:
            endpoint: API端点信息
            positive_headers: 正向测试的headers
            spec_data: 完整的API规范数据
            
        Returns:
            负向测试headers场景字典
        """
        negative_scenarios = {}
        
        # 认证错误场景
        if self._has_auth(spec_data):
            # 缺失认证headers
            auth_missing_headers = {k: v for k, v in positive_headers.items() 
                                  if not k.startswith("Authorization") and not k.startswith("X-API-Key")}
            negative_scenarios["negative_auth_missing"] = auth_missing_headers
            
            # 无效认证headers
            invalid_auth_headers = positive_headers.copy()
            if "Authorization" in invalid_auth_headers:
                invalid_auth_headers["Authorization"] = "Bearer invalid-token"
            elif any(k.startswith("X-API-Key") for k in invalid_auth_headers):
                for k in invalid_auth_headers:
                    if k.startswith("X-API-Key"):
                        invalid_auth_headers[k] = "invalid-key"
            negative_scenarios["negative_auth_invalid"] = invalid_auth_headers
        
        # Content-Type错误场景
        if "Content-Type" in positive_headers:
            wrong_content_type_headers = positive_headers.copy()
            wrong_content_type_headers["Content-Type"] = "text/plain"
            negative_scenarios["negative_content_type"] = wrong_content_type_headers
        
        # Accept错误场景
        if "Accept" in positive_headers:
            wrong_accept_headers = positive_headers.copy()
            wrong_accept_headers["Accept"] = "application/xml"
            negative_scenarios["negative_accept"] = wrong_accept_headers
        
        return negative_scenarios
    
    def _has_auth(self, spec_data: Optional[Dict[str, Any]]) -> bool:
        """检查API是否需要认证。
        
        Args:
            spec_data: 完整的API规范数据
            
        Returns:
            是否需要认证
        """
        if not spec_data:
            return False
        
        # 检查是否有security schemes定义
        has_schemes = (
            ("components" in spec_data and "securitySchemes" in spec_data["components"]) or
            ("securityDefinitions" in spec_data)
        )
        
        # 检查是否有全局security要求
        has_security = "security" in spec_data and bool(spec_data["security"])
        
        return has_schemes or has_security
    
    def get_recommended_headers(self, endpoint: APIEndpoint, test_type: str = "positive", spec_data: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """获取推荐的headers。
        
        Args:
            endpoint: API端点信息
            test_type: 测试类型 ("positive", "negative_auth", etc.)
            spec_data: 完整的API规范数据
            
        Returns:
            推荐的headers字典
        """
        all_scenarios = self.analyze_headers(endpoint, spec_data)
        return all_scenarios.get(test_type, all_scenarios.get("positive", {}))