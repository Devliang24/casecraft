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
        
        # First check endpoint-level security
        if hasattr(endpoint, 'security') and endpoint.security is not None:
            # Endpoint has specific security requirements
            if not endpoint.security:
                # Empty array means no authentication required
                return {}
            
            # Extract auth type from endpoint security
            auth_type = self._detect_auth_type_from_security(endpoint.security, spec_data)
        else:
            # Check if there's global security requirement
            global_security = spec_data.get('security', None)
            if global_security is None:
                # No security requirement at all (neither endpoint nor global)
                return {}
            elif not global_security:
                # Empty global security array means no auth
                return {}
            else:
                # Use global security requirement
                auth_type = self._detect_auth_type_from_security(global_security, spec_data)
        
        # Generate headers based on auth type
        if auth_type == AuthType.BEARER_TOKEN:
            return {"Authorization": "Bearer ${AUTH_TOKEN}"}
        elif auth_type == AuthType.API_KEY:
            return self._get_api_key_headers(spec_data)
        elif auth_type == AuthType.BASIC_AUTH:
            return {"Authorization": "Basic ${BASIC_CREDENTIALS}"}
        elif auth_type == AuthType.OAUTH2:
            return {"Authorization": "Bearer ${OAUTH_TOKEN}"}
        
        return {}
    
    def _detect_auth_type_from_security(self, security: List[Dict[str, List[str]]], spec_data: Dict[str, Any]) -> Optional[AuthType]:
        """从端点的security定义中检测认证类型。
        
        Args:
            security: 端点的security要求列表
            spec_data: 完整的API规范数据
            
        Returns:
            检测到的认证类型
        """
        if not security or not spec_data:
            return None
        
        # Security is a list of requirement objects
        # Each object contains scheme names as keys
        for requirement in security:
            for scheme_name in requirement.keys():
                # Look up the scheme in components/securitySchemes (OpenAPI 3)
                if "components" in spec_data and "securitySchemes" in spec_data["components"]:
                    schemes = spec_data["components"]["securitySchemes"]
                    if scheme_name in schemes:
                        scheme = schemes[scheme_name]
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
                
                # Look up in securityDefinitions (Swagger 2)
                if "securityDefinitions" in spec_data:
                    definitions = spec_data["securityDefinitions"]
                    if scheme_name in definitions:
                        definition = definitions[scheme_name]
                        def_type = definition.get("type", "").lower()
                        
                        if def_type == "oauth2":
                            return AuthType.OAUTH2
                        elif def_type == "apikey":
                            return AuthType.API_KEY
                        elif def_type == "basic":
                            return AuthType.BASIC_AUTH
                
                # Handle common scheme names even without definitions
                scheme_lower = scheme_name.lower()
                if "basic" in scheme_lower:
                    return AuthType.BASIC_AUTH
                elif "bearer" in scheme_lower or "jwt" in scheme_lower:
                    return AuthType.BEARER_TOKEN
                elif "apikey" in scheme_lower or "api_key" in scheme_lower:
                    return AuthType.API_KEY
                elif "oauth" in scheme_lower:
                    return AuthType.OAUTH2
        
        return None
    
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
                    return {header_name: "${API_KEY}"}
        
        # 检查Swagger 2.0
        if "securityDefinitions" in spec_data:
            definitions = spec_data["securityDefinitions"]
            
            for def_name, definition in definitions.items():
                if definition.get("type") == "apiKey" and definition.get("in") == "header":
                    header_name = definition.get("name", "X-API-Key")
                    return {header_name: "${API_KEY}"}
        
        # 默认API Key header
        return {"X-API-Key": "${API_KEY}"}
    
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
                invalid_auth_headers["Authorization"] = "Bearer ${INVALID_TOKEN}"
            elif any(k.startswith("X-API-Key") for k in invalid_auth_headers):
                for k in invalid_auth_headers:
                    if k.startswith("X-API-Key"):
                        invalid_auth_headers[k] = "${INVALID_API_KEY}"
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
    
    def analyze_response_headers(self, endpoint: APIEndpoint, status_code: str = "200") -> Dict[str, str]:
        """分析并生成期望的响应头。
        
        Args:
            endpoint: API端点信息
            status_code: HTTP状态码
            
        Returns:
            期望的响应头字典
        """
        response_headers = {}
        
        # 基础响应头
        response_headers["Content-Type"] = "application/json"
        
        # 基于状态码的响应头
        if status_code == "201":
            response_headers["Location"] = "<created-resource-url>"
        elif status_code in ["200", "201"] and endpoint.method in ["POST", "PUT", "PATCH"]:
            response_headers["Location"] = "<resource-url>"
        
        # 基于HTTP方法的响应头
        if endpoint.method == "GET" and status_code == "200":
            # GET请求的缓存头
            response_headers["Cache-Control"] = "max-age=300"
            response_headers["ETag"] = "<etag-value>"
            response_headers["Last-Modified"] = "<timestamp>"
        
        # 基于端点路径的响应头
        if "/api/" in endpoint.path.lower():
            response_headers["X-API-Version"] = "v1"
        
        # 分页相关的响应头（针对列表接口）
        if ("list" in endpoint.path.lower() or 
            "search" in endpoint.path.lower() or 
            endpoint.path.endswith("s")):
            if status_code == "200":
                response_headers["X-Total-Count"] = "<total-items>"
                response_headers["X-Page-Size"] = "<page-size>"
                response_headers["X-Current-Page"] = "<current-page>"
        
        # 安全相关的响应头
        response_headers["X-Content-Type-Options"] = "nosniff"
        response_headers["X-Frame-Options"] = "DENY"
        
        # 速率限制相关的响应头
        response_headers["X-RateLimit-Limit"] = "<limit>"
        response_headers["X-RateLimit-Remaining"] = "<remaining>"
        response_headers["X-RateLimit-Reset"] = "<reset-time>"
        
        # 基于端点的响应内容分析
        if endpoint.responses and status_code in endpoint.responses:
            response_def = endpoint.responses[status_code]
            
            # 从OpenAPI规范中提取响应头定义
            if "headers" in response_def:
                for header_name, header_def in response_def["headers"].items():
                    if "schema" in header_def:
                        schema = header_def["schema"]
                        if "example" in schema:
                            response_headers[header_name] = schema["example"]
                        elif "default" in schema:
                            response_headers[header_name] = schema["default"]
                        else:
                            response_headers[header_name] = "<header-value>"
            
            # 基于内容类型的响应头
            if "content" in response_def:
                for content_type in response_def["content"].keys():
                    if "json" in content_type.lower():
                        response_headers["Content-Type"] = content_type
                        break
                    elif "xml" in content_type.lower():
                        response_headers["Content-Type"] = content_type
                        break
        
        return response_headers
    
    def get_content_validation_rules(self, endpoint: APIEndpoint, status_code: str = "200") -> Dict[str, Any]:
        """获取响应内容验证规则。
        
        Args:
            endpoint: API端点信息
            status_code: HTTP状态码
            
        Returns:
            内容验证规则字典
        """
        validation_rules = {}
        
        # 基于状态码的基础验证规则
        if status_code == "200":
            if endpoint.method == "GET":
                validation_rules["response_not_empty"] = True
                if "list" in endpoint.path.lower() or endpoint.path.endswith("s"):
                    validation_rules["is_array"] = True
                    validation_rules["array_items_structure"] = True
                else:
                    validation_rules["is_object"] = True
            elif endpoint.method in ["POST", "PUT", "PATCH"]:
                validation_rules["resource_id_present"] = True
                validation_rules["operation_success"] = True
        
        elif status_code == "201":
            validation_rules["resource_created"] = True
            validation_rules["new_resource_id"] = True
            validation_rules["creation_timestamp"] = True
        
        elif status_code == "400":
            validation_rules["error_message_present"] = True
            validation_rules["error_code_present"] = True
            validation_rules["validation_details"] = True
        
        elif status_code == "401":
            validation_rules["auth_error_message"] = "Authentication required"
            validation_rules["error_code"] = "UNAUTHORIZED"
        
        elif status_code == "403":
            validation_rules["auth_error_message"] = "Access denied"
            validation_rules["error_code"] = "FORBIDDEN"
        
        elif status_code == "404":
            validation_rules["error_message"] = "Resource not found"
            validation_rules["error_code"] = "NOT_FOUND"
        
        elif status_code == "422":
            validation_rules["validation_errors_array"] = True
            validation_rules["field_specific_errors"] = True
        
        # 从OpenAPI规范中提取详细的验证规则
        if endpoint.responses and status_code in endpoint.responses:
            response_def = endpoint.responses[status_code]
            
            if "content" in response_def:
                for content_type, content_def in response_def["content"].items():
                    if "json" in content_type.lower() and "schema" in content_def:
                        schema = content_def["schema"]
                        
                        # 提取必填字段
                        if "required" in schema:
                            validation_rules["required_fields"] = schema["required"]
                        
                        # 提取字段类型验证
                        if "properties" in schema:
                            field_types = {}
                            for field_name, field_schema in schema["properties"].items():
                                if "type" in field_schema:
                                    field_types[field_name] = field_schema["type"]
                            if field_types:
                                validation_rules["field_types"] = field_types
                        
                        # 提取格式验证
                        if "format" in schema:
                            validation_rules["format_validation"] = schema["format"]
                        
                        # 提取枚举值验证
                        if "enum" in schema:
                            validation_rules["enum_validation"] = schema["enum"]
                        
                        # 提取数组相关验证
                        if schema.get("type") == "array" and "items" in schema:
                            validation_rules["array_item_validation"] = True
                            if "minItems" in schema:
                                validation_rules["min_items"] = schema["minItems"]
                            if "maxItems" in schema:
                                validation_rules["max_items"] = schema["maxItems"]
                        
                        break
        
        return validation_rules