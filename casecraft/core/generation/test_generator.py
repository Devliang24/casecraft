"""Test case generator using LLM."""

import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from jsonschema import ValidationError, validate
from pydantic import ValidationError as PydanticValidationError

from casecraft.core.generation.llm_client import LLMClient, LLMError
from casecraft.core.parsing.headers_analyzer import HeadersAnalyzer
from casecraft.models.api_spec import APIEndpoint
from casecraft.models.test_case import TestCase, TestCaseCollection, TestType
from casecraft.models.usage import TokenUsage
from casecraft.utils.json_cleaner import clean_json_response
from casecraft.utils.logging import get_logger


class TestGeneratorError(Exception):
    """Test generation related errors."""
    pass


@dataclass
class GenerationResult:
    """Result of test case generation including token usage."""
    
    test_cases: TestCaseCollection
    token_usage: Optional[TokenUsage] = None


class TestCaseGenerator:
    """Generates test cases for API endpoints using LLM."""
    
    def __init__(self, llm_client: LLMClient, api_version: Optional[str] = None):
        """Initialize test case generator.
        
        Args:
            llm_client: LLM client instance
            api_version: API version string
        """
        self.llm_client = llm_client
        self.api_version = api_version
        self.headers_analyzer = HeadersAnalyzer()
        self.logger = get_logger("test_generator")
        self._test_case_schema = self._get_test_case_schema()
    
    async def generate_test_cases(self, endpoint: APIEndpoint) -> GenerationResult:
        """Generate test cases for an API endpoint.
        
        Args:
            endpoint: API endpoint to generate tests for
            
        Returns:
            Generation result including test cases and token usage information
            
        Raises:
            TestGeneratorError: If test generation fails
        """
        try:
            # Generate test cases using LLM
            prompt = self._build_prompt(endpoint)
            system_prompt = self._get_system_prompt()
            
            response = await self.llm_client.generate(
                prompt=prompt,
                system_prompt=system_prompt
            )
            
            # Parse and validate LLM response
            test_cases = self._parse_llm_response(response.content, endpoint)
            
            # Enhance test cases with response schemas and smart status codes
            test_cases = self._enhance_test_cases(test_cases, endpoint)
            
            # Create test case collection with metadata
            collection = TestCaseCollection(
                endpoint_id=endpoint.get_endpoint_id(),
                method=endpoint.method,
                path=endpoint.path,
                summary=endpoint.summary,
                description=endpoint.description,
                tags=endpoint.tags,
                test_cases=test_cases
            )
            
            # Set metadata at collection level
            collection.metadata.llm_model = response.model
            collection.metadata.api_version = self.api_version
            
            # Extract token usage from LLM response
            token_usage = None
            if response.usage:
                token_usage = TokenUsage(
                    prompt_tokens=response.usage.get("prompt_tokens", 0),
                    completion_tokens=response.usage.get("completion_tokens", 0),
                    total_tokens=response.usage.get("total_tokens", 0),
                    model=response.model,
                    endpoint_id=endpoint.get_endpoint_id(),
                    retry_count=response.retry_count
                )
            
            return GenerationResult(
                test_cases=collection,
                token_usage=token_usage
            )
            
        except Exception as e:
            raise TestGeneratorError(
                f"Failed to generate test cases for {endpoint.get_endpoint_id()}: {e}"
            ) from e
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for LLM."""
        return """你是一个API用例设计测试专家。根据提供的API规范和复杂度要求生成测试用例。

生成原则：
1. 根据接口复杂度生成适量的测试用例，避免冗余
2. 每个测试用例都应该有明确的测试目的和价值
3. 优先覆盖关键场景，不要为了凑数而生成无意义的用例

测试用例要求：
- 每个测试用例必须有test_id（从1开始的递增编号）
- 使用中文命名，name和description都用中文描述
- 选择合适的状态码：200(成功)、400(参数错误)、404(资源不存在)、422(验证失败)、401(未认证)、403(无权限)
- 测试数据要真实且简短
- 确保测试用例具有实际意义，避免重复或无效的测试

质量优于数量：宁可生成少一些高质量的测试用例，也不要生成大量重复或无意义的用例。

Tags设置规则：
每个测试用例必须包含有意义的tags标签，具体规则如下：
1. 继承端点标签：从端点的tags字段继承，如["Authentication", "Products"]
2. 测试类型标签：根据test_type添加对应标签，如["positive", "negative", "boundary"]
3. 业务场景标签：根据测试内容添加具体场景标签，如：
   - 用户管理: ["user-management", "registration", "login"]
   - 数据验证: ["validation", "input-validation", "format-check"]
   - 权限控制: ["authorization", "permission", "access-control"]
   - 错误处理: ["error-handling", "edge-case"]
   - 性能测试: ["performance", "load"]
4. 示例tags组合：
   - 正向测试: ["Authentication", "positive", "user-registration"]
   - 负向测试: ["Authentication", "negative", "validation", "input-validation"]
   - 边界测试: ["Authentication", "boundary", "edge-case"]

Headers设置智能规则：
1. 基于HTTP方法的Headers：
   - GET: 添加 "Accept": "application/json"
   - POST/PUT/PATCH: 添加 "Content-Type": "application/json", "Accept": "application/json"
   - DELETE: 添加 "Accept": "application/json"

2. 基于认证要求的Headers：
   - Bearer Token认证: 添加 "Authorization": "Bearer ${AUTH_TOKEN}"
   - API Key认证: 添加 "X-API-Key": "${API_KEY}" 或相应header
   - Basic Auth认证: 添加 "Authorization": "Basic ${BASIC_CREDENTIALS}"
   - 无认证要求: 只添加基本的Accept/Content-Type headers

3. 基于请求体类型的Headers：
   - JSON请求体: "Content-Type": "application/json"
   - 表单数据: "Content-Type": "application/x-www-form-urlencoded"
   - 文件上传: "Content-Type": "multipart/form-data"

4. 负向测试的Headers策略：
   - 缺失认证headers (返回401/403)
   - 错误的Content-Type (返回415)
   - 无效的Accept头 (返回406)
   - 其他情况可以为空

5. 参数生成智能规则：
   - 路径参数：如果API路径包含占位符(如{category_id})，path字段保持原样包含占位符，实际值放在path_params中
     示例：path: "/api/v1/categories/{category_id}", path_params: {"category_id": 123}
   - GET/DELETE: 如果路径包含占位符则需要path_params，可能有query_params
   - POST/PUT/PATCH: 通常有body，path_params仅在路径包含占位符时存在，query_params较少使用
   - 极其重要的规则：
     * 当端点有路径参数时，才包含path_params字段，值为具体参数对象
     * 当端点有查询参数时，才包含query_params字段，值为具体参数对象
     * 当端点没有对应参数时，绝对不要包含该字段（不要设为null、{}、""或任何空值）
     * 示例：POST /api/v1/auth/register 只需要 body，不要包含 path_params 或 query_params
     * 示例：GET /api/v1/categories/{id} 需要 path_params: {"id": 1}，不包含 query_params
     * 示例：GET /api/v1/products?limit=10 需要 query_params: {"limit": 10}，不包含 path_params

重要：
- 直接返回JSON数组，不要任何解释或markdown标记
- 确保JSON格式正确，不要包含注释
- 字符串使用双引号，避免特殊字符
- Headers必须基于上述规则智能生成，不要随意设置
- Tags必须基于上述规则智能生成，绝对不能为空数组[]
- 参数字段规则：
  * 有路径参数时才包含path_params字段（不要设为null）
  * 有查询参数时才包含query_params字段（不要设为null）
  * 没有参数时完全省略这些字段
- 每个测试用例必须包含完整的预期验证信息：
  * resp_headers: 响应头验证
  * resp_content: 响应内容断言
  * rules: 业务逻辑验证规则
  * tags: 基于上述规则生成的有意义标签数组（绝不为空）"""
    
    def _build_prompt(self, endpoint: APIEndpoint) -> str:
        """Build prompt for test case generation.
        
        Args:
            endpoint: API endpoint to generate prompt for
            
        Returns:
            Formatted prompt string
        """
        # Evaluate endpoint complexity
        complexity = self._evaluate_endpoint_complexity(endpoint)
        
        # Build endpoint description
        endpoint_info = {
            "method": endpoint.method,
            "path": endpoint.path,
            "summary": endpoint.summary,
            "description": endpoint.description,
            "tags": endpoint.tags
        }
        
        # Add parameters info
        if endpoint.parameters:
            params_info = []
            for param in endpoint.parameters:
                param_info = {
                    "name": param.name,
                    "location": param.location,
                    "type": param.type,
                    "required": param.required,
                    "description": param.description
                }
                if param.param_schema:
                    param_info["schema"] = param.param_schema
                params_info.append(param_info)
            endpoint_info["parameters"] = params_info
        
        # Add request body info
        if endpoint.request_body:
            endpoint_info["requestBody"] = endpoint.request_body
        
        # Add response info
        if endpoint.responses:
            endpoint_info["responses"] = endpoint.responses
        
        # Analyze headers recommendations
        headers_scenarios = self.headers_analyzer.analyze_headers(endpoint)
        
        # Build complexity guidance
        complexity_guidance = f"""
**接口复杂度分析:**
- 复杂度级别: {complexity['complexity_level']}
- 影响因素: {', '.join(complexity['factors']) if complexity['factors'] else '基础接口'}
- 建议生成数量:
  - 总计: {complexity['recommended_counts']['total'][0]}-{complexity['recommended_counts']['total'][1]}个测试用例
  - 正向测试: {complexity['recommended_counts']['positive'][0]}-{complexity['recommended_counts']['positive'][1]}个
  - 负向测试: {complexity['recommended_counts']['negative'][0]}-{complexity['recommended_counts']['negative'][1]}个
  - 边界测试: {complexity['recommended_counts']['boundary'][0]}-{complexity['recommended_counts']['boundary'][1]}个
"""

        # Build the prompt
        prompt = f"""Generate comprehensive test cases for the following API endpoint:

**Endpoint Definition:**
```json
{json.dumps(endpoint_info, indent=2)}
```

{complexity_guidance}

**Headers建议 (智能分析结果):**
- 正向测试建议headers: {json.dumps(headers_scenarios.get('positive', {}), indent=2)}
- 负向测试场景: {list(headers_scenarios.keys())}

**完整的测试用例验证要求:**
1. **状态码验证**: 准确的HTTP状态码期望
2. **响应头验证**: 包括Content-Type、Location、Cache-Control等
3. **响应体结构验证**: 基于OpenAPI schema的结构验证
4. **响应内容验证**: 具体字段值、格式、业务逻辑验证
5. **性能验证**: 响应时间期望
6. **业务规则验证**: 数据一致性、权限控制等

**Required Test Case JSON Schema:**
```json
{json.dumps(self._test_case_schema, indent=2)}
```

请根据接口复杂度生成相应数量的高质量测试用例。每个用例都应该有明确的测试目的，避免重复或无意义的测试。
注意：生成的测试用例应该包含完整的预期验证，不仅仅是状态码，还要包括响应头、响应内容、业务规则等全面的验证。

Return the test cases as a JSON array:"""
        
        return prompt
    
    def _parse_llm_response(self, response_content: str, endpoint: APIEndpoint) -> List[TestCase]:
        """Parse and validate LLM response.
        
        Args:
            response_content: Raw LLM response content
            endpoint: API endpoint for context
            
        Returns:
            List of validated test cases
            
        Raises:
            TestGeneratorError: If response is invalid
        """
        # Use JSON cleaner to handle various issues
        try:
            test_data = clean_json_response(response_content)
        except json.JSONDecodeError as e:
            # Log the problematic content for debugging
            self.logger.error(f"Failed to parse JSON: {str(e)[:100]}")
            self.logger.debug(f"Raw content: {response_content[:500]}...")
            raise TestGeneratorError(f"Invalid JSON in LLM response: {e}")
        
        if not isinstance(test_data, list):
            raise TestGeneratorError("LLM response must be a JSON array of test cases")
        
        # Validate and convert to TestCase objects
        test_cases = []
        for i, test_case_data in enumerate(test_data):
            try:
                # Validate against schema
                validate(test_case_data, self._test_case_schema)
                
                # Clean up null/empty parameters before creating TestCase
                # This ensures we don't have unnecessary null or empty dict fields
                params_to_check = ['path_params', 'query_params']
                for param_field in params_to_check:
                    if param_field in test_case_data:
                        value = test_case_data[param_field]
                        # Remove if None, empty dict, empty string, or string "null"
                        if value is None or value == {} or value == '' or value == 'null':
                            del test_case_data[param_field]
                
                # Convert to TestCase object
                test_case = TestCase(**test_case_data)
                test_cases.append(test_case)
                
            except ValidationError as e:
                raise TestGeneratorError(f"Test case {i} validation error: {e}")
            except PydanticValidationError as e:
                raise TestGeneratorError(f"Test case {i} model error: {e}")
        
        # Validate test case coverage
        self._validate_test_coverage(test_cases, endpoint)
        
        return test_cases
    
    def _validate_test_coverage(self, test_cases: List[TestCase], endpoint: APIEndpoint) -> None:
        """Validate that test cases meet coverage requirements based on endpoint complexity.
        
        Args:
            test_cases: Generated test cases
            endpoint: API endpoint
            
        Raises:
            TestGeneratorError: If coverage requirements not met
        """
        if not test_cases:
            raise TestGeneratorError("No test cases generated")
        
        # Evaluate endpoint complexity to get requirements
        complexity = self._evaluate_endpoint_complexity(endpoint)
        
        # Count test types
        positive_count = sum(1 for tc in test_cases if tc.test_type == TestType.POSITIVE)
        negative_count = sum(1 for tc in test_cases if tc.test_type == TestType.NEGATIVE)
        boundary_count = sum(1 for tc in test_cases if tc.test_type == TestType.BOUNDARY)
        total_count = len(test_cases)
        
        # Get minimum requirements based on complexity
        min_positive = complexity['recommended_counts']['positive'][0]
        min_negative = complexity['recommended_counts']['negative'][0]
        min_total = complexity['recommended_counts']['total'][0]
        
        # Check minimum requirements
        if positive_count < min_positive:
            raise TestGeneratorError(
                f"At least {min_positive} positive test cases are required for "
                f"{complexity['complexity_level']} endpoint, got {positive_count}"
            )
        
        if negative_count < min_negative:
            raise TestGeneratorError(
                f"At least {min_negative} negative test cases are required for "
                f"{complexity['complexity_level']} endpoint, got {negative_count}"
            )
        
        # Check total count
        if total_count < min_total:
            raise TestGeneratorError(
                f"At least {min_total} test cases are required for "
                f"{complexity['complexity_level']} endpoint, got {total_count}"
            )
        
        # Log test case distribution with complexity info
        self.logger.info(f"Generated {total_count} test cases for {complexity['complexity_level']} endpoint ({endpoint.method} {endpoint.path}): {positive_count} positive, {negative_count} negative, {boundary_count} boundary")
        
        # Validate that each test case has required fields
        for i, test_case in enumerate(test_cases):
            if not test_case.name or not test_case.description:
                raise TestGeneratorError(f"Test case {i} missing name or description")
            
            if not test_case.status:
                raise TestGeneratorError(f"Test case {i} missing expected status code")
    
    def _get_test_case_schema(self) -> Dict[str, Any]:
        """Get JSON schema for test case validation."""
        return {
            "type": "object",
            "required": [
                "test_id",
                "name",
                "description", 
                "method",
                "path",
                "status",
                "test_type"
            ],
            "properties": {
                "test_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Test case ID/sequence number"
                },
                "name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Test case name"
                },
                "description": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Test case description"
                },
                "method": {
                    "type": "string",
                    "pattern": "^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)$",
                    "description": "HTTP method"
                },
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "API path"
                },
                "headers": {
                    "type": "object",
                    "description": "Request headers"
                },
                "body": {
                    "oneOf": [
                        {"type": "object"},
                        {"type": "null"}
                    ],
                    "description": "Request body"
                },
                "status": {
                    "type": "integer",
                    "minimum": 100,
                    "maximum": 599,
                    "description": "Expected HTTP status code"
                },
                "resp_schema": {
                    "type": "object",
                    "description": "Expected response schema"
                },
                "test_type": {
                    "type": "string",
                    "enum": ["positive", "negative", "boundary"],
                    "description": "Test case type"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Test tags"
                },
                "resp_headers": {
                    "type": "object",
                    "description": "Expected response headers"
                },
                "resp_content": {
                    "type": "object",
                    "description": "Expected response content assertions"
                },
                "rules": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Business logic validation rules"
                }
            },
            "additionalProperties": False
        }
    
    def _enhance_test_cases(self, test_cases: List[TestCase], endpoint: APIEndpoint) -> List[TestCase]:
        """Enhance test cases with response schemas and improved status codes.
        
        Args:
            test_cases: List of test cases to enhance
            endpoint: API endpoint for context
            
        Returns:
            Enhanced test cases
        """
        # Extract response schemas from endpoint
        response_schemas = self._extract_response_schemas(endpoint)
        
        # Ensure each test case has a proper test_id
        for i, test_case in enumerate(test_cases, 1):
            if not hasattr(test_case, 'test_id') or test_case.test_id is None:
                test_case.test_id = i
            
            status_str = str(test_case.status)
            
            # Add response schema for all cases with defined schemas
            if status_str in response_schemas:
                test_case.resp_schema = response_schemas[status_str]
            else:
                # Provide default schema based on status code
                test_case.resp_schema = self._get_default_response_schema(status_str)
            
            # Add expected response headers
            test_case.resp_headers = self._extract_response_headers(endpoint, status_str)
            
            # Add response content assertions
            content_assertions = self._extract_response_content_assertions(endpoint, status_str)
            if content_assertions:
                test_case.resp_content = content_assertions
            
            # Add business rules based on endpoint characteristics
            business_rules = self._generate_business_rules(test_case, endpoint)
            if business_rules:
                test_case.rules = business_rules
            
            # Improve status codes based on test type and error
            if test_case.test_type == TestType.NEGATIVE:
                test_case.status = self._infer_status_code(test_case, endpoint)
            
            # Ensure test case has meaningful tags
            test_case.tags = self._generate_test_case_tags(test_case, endpoint)
        
        return test_cases
    
    def _extract_response_schemas(self, endpoint: APIEndpoint) -> Dict[str, Dict[str, Any]]:
        """Extract response schemas from endpoint definition.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            Map of status code to response schema
        """
        schemas = {}
        
        for status, response_def in endpoint.responses.items():
            if "content" in response_def:
                # Try to find JSON schema
                for content_type, content_def in response_def["content"].items():
                    if "json" in content_type.lower() and "schema" in content_def:
                        schema = content_def["schema"].copy()
                        # Simplify or remove long titles to save tokens
                        if "title" in schema and len(schema["title"]) > 20:
                            # Create a simple title based on status code
                            status_int = int(status) if status.isdigit() else 200
                            if 200 <= status_int < 300:
                                schema["title"] = "Success Response"
                            elif 400 <= status_int < 500:
                                schema["title"] = "Error Response"
                            else:
                                schema["title"] = f"Response {status}"
                        schemas[status] = schema
                        break
        
        return schemas
    
    def _get_default_response_schema(self, status_code: str) -> Dict[str, Any]:
        """Get default response schema based on status code.
        
        Args:
            status_code: HTTP status code as string
            
        Returns:
            Default response schema
        """
        status_int = int(status_code)
        
        # Success responses (2xx)
        if 200 <= status_int < 300:
            return {
                "type": "object",
                "additionalProperties": True
            }
        
        # Client error responses (4xx)
        elif 400 <= status_int < 500:
            return {
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "message": {"type": "string"},
                    "code": {"type": "string"}
                },
                "additionalProperties": True
            }
        
        # Server error responses (5xx)
        elif 500 <= status_int < 600:
            return {
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "message": {"type": "string"}
                },
                "additionalProperties": True
            }
        
        # Default fallback
        else:
            return {
                "type": "object",
                "additionalProperties": True
            }
    
    def _extract_response_headers(self, endpoint: APIEndpoint, status_code: str) -> Dict[str, Any]:
        """Extract expected response headers for a given status code.
        
        Args:
            endpoint: API endpoint
            status_code: HTTP status code (as string)
            
        Returns:
            Map of header name to expected value or pattern
        """
        headers = {}
        
        # Default headers for all responses
        headers["Content-Type"] = "application/json"
        
        # Extract from endpoint response definition
        if status_code in endpoint.responses:
            response_def = endpoint.responses[status_code]
            if "headers" in response_def:
                for header_name, header_def in response_def["headers"].items():
                    # Extract expected header value or pattern
                    if "schema" in header_def:
                        schema = header_def["schema"]
                        if "example" in schema:
                            headers[header_name] = schema["example"]
                        elif "default" in schema:
                            headers[header_name] = schema["default"]
                        else:
                            # Just indicate the header should be present
                            headers[header_name] = "<any>"
        
        # Add common response headers based on operation type
        if endpoint.method in ["POST", "PUT", "PATCH"] and status_code in ["200", "201"]:
            headers["Location"] = "<resource-url>"
        
        if status_code == "201":
            headers["Location"] = "<created-resource-url>"
        
        # Add cache-related headers for GET requests
        if endpoint.method == "GET" and status_code == "200":
            headers["Cache-Control"] = "max-age=300"
            headers["ETag"] = "<etag-value>"
        
        return headers
    
    def _extract_response_content_assertions(self, endpoint: APIEndpoint, status_code: str) -> Optional[Dict[str, Any]]:
        """Extract content validation assertions for response.
        
        Args:
            endpoint: API endpoint
            status_code: HTTP status code (as string)
            
        Returns:
            Content assertion rules or None
        """
        assertions = {}
        
        # Extract from response schema
        if status_code in endpoint.responses:
            response_def = endpoint.responses[status_code]
            if "content" in response_def:
                for content_type, content_def in response_def["content"].items():
                    if "json" in content_type.lower() and "schema" in content_def:
                        schema = content_def["schema"]
                        
                        # Add schema-based assertions
                        if "properties" in schema:
                            required_fields = schema.get("required", [])
                            if required_fields:
                                assertions["required_fields"] = required_fields
                        
                        # Add type assertions
                        if "type" in schema:
                            assertions["response_type"] = schema["type"]
                        
                        # Add example-based assertions
                        if "example" in schema:
                            assertions["example_match"] = schema["example"]
                        
                        # Add format assertions
                        if "format" in schema:
                            assertions["format"] = schema["format"]
                        
                        break
        
        # Add common assertions based on status code
        if status_code == "200":
            if endpoint.method == "GET":
                assertions["non_empty_response"] = True
        elif status_code == "201":
            assertions["created_resource_id"] = True
        elif status_code == "400":
            assertions["error_message"] = True
            assertions["error_code"] = True
        elif status_code == "404":
            assertions["error_message"] = "Resource not found"
        elif status_code == "422":
            assertions["validation_errors"] = True
        
        return assertions if assertions else None
    
    def _infer_status_code(self, test_case: TestCase, endpoint: APIEndpoint) -> int:
        """Infer appropriate status code based on test case details.
        
        Args:
            test_case: Test case to analyze
            endpoint: API endpoint for context
            
        Returns:
            Inferred status code
        """
        name_lower = test_case.name.lower()
        desc_lower = test_case.description.lower()
        
        # Check for specific error types
        if any(word in name_lower + desc_lower for word in ["missing", "required", "empty"]):
            return 400  # Bad Request for missing required fields
        
        if any(word in name_lower + desc_lower for word in ["invalid type", "string instead", "format"]):
            return 400  # Bad Request for type/format errors
        
        if any(word in name_lower + desc_lower for word in ["not found", "nonexistent", "doesn't exist"]):
            return 404  # Not Found
        
        if any(word in name_lower + desc_lower for word in ["validation", "constraint", "range"]):
            return 422  # Unprocessable Entity for validation errors
        
        if any(word in name_lower + desc_lower for word in ["unauthorized", "authentication"]):
            return 401  # Unauthorized
        
        if any(word in name_lower + desc_lower for word in ["forbidden", "permission", "access"]):
            return 403  # Forbidden
        
        # For path parameter errors, typically 404
        if test_case.path_params and endpoint.path.count("{") > 0:
            return 404
        
        # Default to current status or 400
        return test_case.status if test_case.status in [400, 404, 422] else 400
    
    def _evaluate_endpoint_complexity(self, endpoint: APIEndpoint) -> Dict[str, Any]:
        """Evaluate the complexity of an API endpoint.
        
        Args:
            endpoint: API endpoint to evaluate
            
        Returns:
            Dictionary with complexity metrics and recommended test case counts
        """
        complexity_score = 0
        factors = []
        
        # 1. Parameter complexity
        param_count = len(endpoint.parameters) if endpoint.parameters else 0
        if param_count > 0:
            complexity_score += param_count * 2
            factors.append(f"{param_count} parameters")
        
        # 2. Request body complexity
        if endpoint.request_body:
            body_complexity = self._evaluate_schema_complexity(endpoint.request_body)
            complexity_score += body_complexity
            if body_complexity > 5:
                factors.append("complex request body")
            elif body_complexity > 0:
                factors.append("simple request body")
        
        # 3. Operation type complexity
        if endpoint.method in ["POST", "PUT", "PATCH"]:
            complexity_score += 3
            factors.append(f"{endpoint.method} operation")
        elif endpoint.method == "DELETE":
            complexity_score += 2
            factors.append("DELETE operation")
        
        # 4. Authentication requirements
        has_auth = any(p.name.lower() in ["authorization", "api-key", "x-api-key"] 
                      for p in (endpoint.parameters or []))
        if has_auth:
            complexity_score += 2
            factors.append("authentication required")
        
        # 5. Response complexity
        if endpoint.responses:
            response_count = len(endpoint.responses)
            if response_count > 3:
                complexity_score += 2
                factors.append(f"{response_count} response types")
        
        # Determine recommended test case counts based on complexity
        if complexity_score <= 5:
            # Simple endpoint: 5-6 test cases
            min_total = 5
            max_total = 6
            positive_range = (2, 2)
            negative_range = (2, 3)
            boundary_range = (1, 1)
            complexity_level = "simple"
        elif complexity_score <= 10:
            # Medium complexity: 7-9 test cases
            min_total = 7
            max_total = 9
            positive_range = (2, 3)
            negative_range = (3, 4)
            boundary_range = (1, 2)
            complexity_level = "medium"
        else:
            # Complex endpoint: 10-12 test cases
            min_total = 10
            max_total = 12
            positive_range = (3, 4)
            negative_range = (4, 5)
            boundary_range = (2, 3)
            complexity_level = "complex"
        
        return {
            "complexity_score": complexity_score,
            "complexity_level": complexity_level,
            "factors": factors,
            "recommended_counts": {
                "total": (min_total, max_total),
                "positive": positive_range,
                "negative": negative_range,
                "boundary": boundary_range
            }
        }
    
    def _evaluate_schema_complexity(self, schema: Dict[str, Any]) -> int:
        """Evaluate the complexity of a JSON schema.
        
        Args:
            schema: JSON schema to evaluate
            
        Returns:
            Complexity score
        """
        score = 0
        
        if isinstance(schema, dict):
            # Check for content types
            if "content" in schema:
                for content_type, content_schema in schema.get("content", {}).items():
                    if "schema" in content_schema:
                        score += self._evaluate_schema_complexity(content_schema["schema"])
            
            # Check for object properties
            if schema.get("type") == "object":
                properties = schema.get("properties", {})
                score += len(properties)
                
                # Check for required fields
                required = schema.get("required", [])
                score += len(required)
                
                # Check for nested objects
                for prop_schema in properties.values():
                    if isinstance(prop_schema, dict) and prop_schema.get("type") == "object":
                        score += 2  # Nested objects add complexity
                    elif isinstance(prop_schema, dict) and prop_schema.get("type") == "array":
                        score += 1  # Arrays add some complexity
            
            # Check for arrays
            elif schema.get("type") == "array":
                score += 2
                if "items" in schema:
                    score += self._evaluate_schema_complexity(schema["items"])
        
        return score
    
    def _generate_business_rules(self, test_case: TestCase, endpoint: APIEndpoint) -> List[str]:
        """Generate business logic validation rules for a test case.
        
        Args:
            test_case: Test case to generate rules for
            endpoint: API endpoint context
            
        Returns:
            List of business rule descriptions
        """
        rules = []
        
        # Rules based on HTTP method
        if endpoint.method == "POST" and test_case.test_type == TestType.POSITIVE:
            rules.append("创建的资源应具有唯一ID")
            rules.append("响应应包含资源位置")
        
        elif endpoint.method == "PUT" and test_case.test_type == TestType.POSITIVE:
            rules.append("更新的资源应保持数据完整性")
            rules.append("版本号或时间戳应被更新")
        
        elif endpoint.method == "DELETE" and test_case.test_type == TestType.POSITIVE:
            rules.append("资源应被标记为已删除或移除")
            rules.append("后续的GET请求应返回404")
        
        elif endpoint.method == "GET" and test_case.test_type == TestType.POSITIVE:
            rules.append("响应数据应与数据库保持一致")
            if "list" in endpoint.path.lower() or "search" in endpoint.path.lower():
                rules.append("分页应被正确处理")
                rules.append("结果应匹配过滤条件")
        
        # Rules based on authentication
        has_auth = any(p.name.lower() in ["authorization", "api-key", "x-api-key"] 
                      for p in (endpoint.parameters or []))
        
        if has_auth and test_case.test_type == TestType.NEGATIVE:
            if "unauthorized" in test_case.description.lower():
                rules.append("无有效认证时应拒绝访问")
            elif "forbidden" in test_case.description.lower():
                rules.append("应验证用户权限")
        
        # Rules based on path parameters
        if test_case.path_params and "{id}" in endpoint.path:
            if test_case.test_type == TestType.NEGATIVE:
                rules.append("无效的ID格式应被拒绝")
                rules.append("不存在的ID应返回适当的错误")
            else:
                rules.append("ID应引用存在的资源")
        
        # Rules for validation scenarios
        if test_case.test_type == TestType.NEGATIVE and "validation" in test_case.description.lower():
            rules.append("输入验证错误应被清晰描述")
            rules.append("错误响应应包含字段级别的错误信息")
        
        # Rules for boundary cases
        if test_case.test_type == TestType.BOUNDARY:
            rules.append("边界值应被优雅地处理")
            rules.append("系统限制应被遵守")
        
        return rules
    
    def _generate_test_case_tags(self, test_case: TestCase, endpoint: APIEndpoint) -> List[str]:
        """Generate meaningful tags for a test case.
        
        Args:
            test_case: Test case to generate tags for
            endpoint: API endpoint context
            
        Returns:
            List of meaningful tags
        """
        tags = set()
        
        # 1. Inherit endpoint tags (normalize to lowercase)
        if endpoint.tags:
            tags.update([tag.lower() for tag in endpoint.tags])
        
        # 2. Add test type tag
        if hasattr(test_case.test_type, 'value'):
            tags.add(test_case.test_type.value)  # positive, negative, boundary
        else:
            tags.add(str(test_case.test_type).lower())  # fallback for string values
        
        # 3. Add business scenario tags based on endpoint path and description
        path_lower = endpoint.path.lower()
        desc_lower = (test_case.description or "").lower()
        name_lower = (test_case.name or "").lower()
        endpoint_desc = (endpoint.description or "").lower()
        
        # User management related
        if any(word in path_lower for word in ["auth", "user", "login", "register"]):
            if "register" in path_lower or "register" in desc_lower:
                tags.add("user-registration")
            if "login" in path_lower or "login" in desc_lower:
                tags.add("user-login")
            if "user" in path_lower:
                tags.add("user-management")
        
        # Product/Category management
        if "product" in path_lower:
            tags.add("product-management")
        if "category" in path_lower:
            tags.add("category-management")
        
        # Shopping cart
        if "cart" in path_lower:
            tags.add("shopping-cart")
        
        # Orders
        if "order" in path_lower:
            tags.add("order-management")
        
        # 4. Add validation related tags
        if any(word in desc_lower + name_lower for word in ["validation", "invalid", "missing", "required", "format"]):
            tags.add("validation")
            if any(word in desc_lower + name_lower for word in ["email", "format", "type"]):
                tags.add("input-validation")
        
        # 5. Add authentication/authorization tags
        if any(word in desc_lower + name_lower for word in ["unauthorized", "forbidden", "permission", "access"]):
            tags.add("access-control")
        
        # 6. Add error handling tags for negative tests
        if test_case.test_type == TestType.NEGATIVE:
            tags.add("error-handling")
            
            # Specific error types
            if any(word in desc_lower + name_lower for word in ["not found", "nonexistent", "doesn't exist"]):
                tags.add("resource-not-found")
            elif any(word in desc_lower + name_lower for word in ["duplicate", "exist", "unique"]):
                tags.add("duplicate-handling")
            elif any(word in desc_lower + name_lower for word in ["weak", "password", "security"]):
                tags.add("security-validation")
        
        # 7. Add boundary/edge case tags
        if test_case.test_type == TestType.BOUNDARY:
            tags.add("edge-case")
            if any(word in desc_lower + name_lower for word in ["boundary", "limit", "maximum", "minimum"]):
                tags.add("boundary-testing")
        
        # 8. HTTP method specific tags
        if endpoint.method in ["POST", "PUT", "PATCH"]:
            if test_case.test_type == TestType.POSITIVE:
                tags.add("data-creation" if endpoint.method == "POST" else "data-modification")
        
        # Convert back to list and sort for consistency
        return sorted(list(tags))