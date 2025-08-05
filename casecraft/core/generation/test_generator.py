"""Test case generator using LLM."""

import json
from typing import Any, Dict, List, Optional

from jsonschema import ValidationError, validate
from pydantic import ValidationError as PydanticValidationError

from casecraft.core.generation.llm_client import LLMClient, LLMError
from casecraft.core.parsing.headers_analyzer import HeadersAnalyzer
from casecraft.models.api_spec import APIEndpoint
from casecraft.models.test_case import TestCase, TestCaseCollection, TestType
from casecraft.utils.json_cleaner import clean_json_response
from casecraft.utils.logging import get_logger


class TestGeneratorError(Exception):
    """Test generation related errors."""
    pass


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
    
    async def generate_test_cases(self, endpoint: APIEndpoint) -> TestCaseCollection:
        """Generate test cases for an API endpoint.
        
        Args:
            endpoint: API endpoint to generate tests for
            
        Returns:
            Collection of generated test cases
            
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
            
            # Update metadata with LLM model and API version
            for test_case in test_cases:
                test_case.metadata.llm_model = response.model
                test_case.metadata.api_version = self.api_version
            
            return TestCaseCollection(
                endpoint_id=endpoint.get_endpoint_id(),
                method=endpoint.method,
                path=endpoint.path,
                summary=endpoint.summary,
                description=endpoint.description,
                tags=endpoint.tags,
                test_cases=test_cases
            )
            
        except Exception as e:
            raise TestGeneratorError(
                f"Failed to generate test cases for {endpoint.get_endpoint_id()}: {e}"
            ) from e
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for LLM."""
        return """你是一个API测试专家。根据提供的API规范生成测试用例。

生成要求：
1. 正向测试(必须2个)：包含所有必填参数的有效请求，测试不同的有效场景
2. 负向测试(3-4个)：缺少参数、类型错误、格式错误、超出范围
3. 边界测试(1-2个)：最小值、最大值、空值

测试用例限制：
- 总数6-8个测试用例，确保正向测试不少于2个
- 使用中文命名，name和description都用中文描述
- 选择合适的状态码：200(成功)、400(参数错误)、404(资源不存在)、422(验证失败)
- 测试数据要真实且简短

Headers设置智能规则：
1. 基于HTTP方法的Headers：
   - GET: 添加 "Accept": "application/json"
   - POST/PUT/PATCH: 添加 "Content-Type": "application/json", "Accept": "application/json"
   - DELETE: 添加 "Accept": "application/json"

2. 基于认证要求的Headers：
   - Bearer Token认证: 添加 "Authorization": "Bearer <valid-token>"
   - API Key认证: 添加 "X-API-Key": "<valid-key>" 或相应header
   - Basic Auth认证: 添加 "Authorization": "Basic <credentials>"
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

重要：
- 直接返回JSON数组，不要任何解释或markdown标记
- 确保JSON格式正确，不要包含注释
- 字符串使用双引号，避免特殊字符
- Headers必须基于上述规则智能生成，不要随意设置"""
    
    def _build_prompt(self, endpoint: APIEndpoint) -> str:
        """Build prompt for test case generation.
        
        Args:
            endpoint: API endpoint to generate prompt for
            
        Returns:
            Formatted prompt string
        """
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
        
        # Build the prompt
        prompt = f"""Generate comprehensive test cases for the following API endpoint:

**Endpoint Definition:**
```json
{json.dumps(endpoint_info, indent=2)}
```

**Headers建议 (智能分析结果):**
- 正向测试建议headers: {json.dumps(headers_scenarios.get('positive', {}), indent=2)}
- 负向测试场景: {list(headers_scenarios.keys())}
```

**Required Test Case JSON Schema:**
```json
{json.dumps(self._test_case_schema, indent=2)}
```

Generate test cases that thoroughly test this endpoint. Include positive cases, negative cases, and boundary cases as specified in the system prompt.

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
        """Validate that test cases meet coverage requirements.
        
        Args:
            test_cases: Generated test cases
            endpoint: API endpoint
            
        Raises:
            TestGeneratorError: If coverage requirements not met
        """
        if not test_cases:
            raise TestGeneratorError("No test cases generated")
        
        # Count test types
        positive_count = sum(1 for tc in test_cases if tc.test_type == TestType.POSITIVE)
        negative_count = sum(1 for tc in test_cases if tc.test_type == TestType.NEGATIVE)
        boundary_count = sum(1 for tc in test_cases if tc.test_type == TestType.BOUNDARY)
        
        # Check minimum requirements
        if positive_count < 2:
            raise TestGeneratorError("At least 2 positive test cases are required")
        
        if negative_count < 3:
            raise TestGeneratorError("At least 3 negative test cases are required")
        
        # Validate that each test case has required fields
        for i, test_case in enumerate(test_cases):
            if not test_case.name or not test_case.description:
                raise TestGeneratorError(f"Test case {i} missing name or description")
            
            if not test_case.expected_status:
                raise TestGeneratorError(f"Test case {i} missing expected status code")
    
    def _get_test_case_schema(self) -> Dict[str, Any]:
        """Get JSON schema for test case validation."""
        return {
            "type": "object",
            "required": [
                "name",
                "description", 
                "method",
                "path",
                "expected_status",
                "test_type"
            ],
            "properties": {
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
                "path_params": {
                    "type": "object", 
                    "description": "Path parameters"
                },
                "query_params": {
                    "type": "object",
                    "description": "Query parameters"
                },
                "body": {
                    "oneOf": [
                        {"type": "object"},
                        {"type": "null"}
                    ],
                    "description": "Request body"
                },
                "expected_status": {
                    "type": "integer",
                    "minimum": 100,
                    "maximum": 599,
                    "description": "Expected HTTP status code"
                },
                "expected_response_schema": {
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
        
        for test_case in test_cases:
            # Add response schema for successful cases
            if test_case.test_type == TestType.POSITIVE and test_case.expected_status == 200:
                if "200" in response_schemas:
                    test_case.expected_response_schema = response_schemas["200"]
            
            # Improve status codes based on test type and error
            if test_case.test_type == TestType.NEGATIVE:
                test_case.expected_status = self._infer_status_code(test_case, endpoint)
        
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
                        schemas[status] = content_def["schema"]
                        break
        
        return schemas
    
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
        return test_case.expected_status if test_case.expected_status in [400, 404, 422] else 400