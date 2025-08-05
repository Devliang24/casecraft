"""Tests for test case generator."""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from casecraft.core.generation.test_generator import TestCaseGenerator, TestGeneratorError
from casecraft.core.generation.llm_client import LLMResponse
from casecraft.models.api_spec import APIEndpoint, APIParameter
from casecraft.models.test_case import TestType


class TestTestCaseGenerator:
    """Test test case generator functionality."""
    
    def test_init(self):
        """Test generator initialization."""
        llm_client = Mock()
        generator = TestCaseGenerator(llm_client)
        
        assert generator.llm_client == llm_client
        assert generator.api_version is None
        assert generator._test_case_schema is not None
        
        # Test with API version
        generator = TestCaseGenerator(llm_client, api_version="1.0.0")
        assert generator.api_version == "1.0.0"
    
    def test_system_prompt_chinese(self):
        """Test that system prompt requires Chinese names and descriptions."""
        llm_client = Mock()
        generator = TestCaseGenerator(llm_client)
        
        system_prompt = generator._get_system_prompt()
        assert "使用中文命名" in system_prompt
        assert "name和description都用中文描述" in system_prompt
    
    @pytest.mark.asyncio
    async def test_generate_test_cases_success(self):
        """Test successful test case generation."""
        llm_client = AsyncMock()
        generator = TestCaseGenerator(llm_client)
        
        # Create test endpoint
        endpoint = APIEndpoint(
            method="POST",
            path="/users",
            summary="Create user",
            tags=["users"],
            parameters=[
                APIParameter(
                    name="Content-Type",
                    location="header",
                    type="string",
                    required=True
                )
            ]
        )
        
        # Mock LLM response with valid test cases (10+ test cases)
        test_cases_json = [
            # Positive test cases (3)
            {
                "test_id": 1,
                "name": "创建用户成功",
                "description": "使用有效数据成功创建用户",
                "method": "POST",
                "path": "/users",
                "headers": {"Content-Type": "application/json"},
                "path_params": {},
                "query_params": {},
                "body": {"name": "John Doe", "email": "john@example.com"},
                "expected_status": 201,
                "expected_response_headers": {"Content-Type": "application/json", "Location": "<created-resource-url>"},
                "expected_response_content": {"resource_created": True, "new_resource_id": True},
                "business_rules": ["创建的资源应具有唯一ID"],
                "test_type": "positive",
                "tags": ["users"]
            },
            {
                "test_id": 2,
                "name": "创建管理员用户",
                "description": "创建具有管理员角色的用户",
                "method": "POST",
                "path": "/users",
                "headers": {"Content-Type": "application/json"},
                "path_params": {},
                "query_params": {},
                "body": {"name": "Admin User", "email": "admin@example.com", "role": "admin"},
                "expected_status": 201,
                "expected_response_headers": {"Content-Type": "application/json", "Location": "<created-resource-url>"},
                "expected_response_content": {"resource_created": True, "new_resource_id": True},
                "business_rules": ["创建的资源应具有唯一ID"],
                "test_type": "positive",
                "tags": ["users"]
            },
            {
                "test_id": 3,
                "name": "创建用户包含可选字段",
                "description": "创建用户时包含所有可选字段",
                "method": "POST",
                "path": "/users",
                "headers": {"Content-Type": "application/json"},
                "path_params": {},
                "query_params": {},
                "body": {"name": "Full User", "email": "full@example.com", "phone": "123456789", "age": 25},
                "expected_status": 201,
                "expected_response_headers": {"Content-Type": "application/json", "Location": "<created-resource-url>"},
                "expected_response_content": {"resource_created": True, "new_resource_id": True},
                "business_rules": ["创建的资源应具有唯一ID"],
                "test_type": "positive",
                "tags": ["users"]
            },
            # Negative test cases (4)
            {
                "test_id": 4,
                "name": "缺少必填字段name",
                "description": "创建用户时缺少必填字段name",
                "method": "POST", 
                "path": "/users",
                "headers": {"Content-Type": "application/json"},
                "path_params": {},
                "query_params": {},
                "body": {"email": "john@example.com"},
                "expected_status": 400,
                "test_type": "negative",
                "tags": ["users"]
            },
            {
                "test_id": 5,
                "name": "邮箱格式错误",
                "description": "使用无效的邮箱格式创建用户",
                "method": "POST",
                "path": "/users", 
                "headers": {"Content-Type": "application/json"},
                "path_params": {},
                "query_params": {},
                "body": {"name": "John Doe", "email": "invalid-email"},
                "expected_status": 400,
                "test_type": "negative",
                "tags": ["users"]
            },
            {
                "test_id": 6,
                "name": "请求体为空",
                "description": "发送空的请求体",
                "method": "POST",
                "path": "/users",
                "headers": {"Content-Type": "application/json"},
                "path_params": {},
                "query_params": {},
                "body": {},
                "expected_status": 400,
                "test_type": "negative",
                "tags": ["users"]
            },
            {
                "test_id": 7,
                "name": "字段类型错误",
                "description": "name字段使用数字类型而非字符串",
                "method": "POST",
                "path": "/users",
                "headers": {"Content-Type": "application/json"},
                "path_params": {},
                "query_params": {},
                "body": {"name": 12345, "email": "test@example.com"},
                "expected_status": 400,
                "test_type": "negative",
                "tags": ["users"]
            },
            # Boundary test cases (3)
            {
                "test_id": 8,
                "name": "用户名最大长度",
                "description": "使用最大允许长度的用户名",
                "method": "POST",
                "path": "/users",
                "headers": {"Content-Type": "application/json"},
                "path_params": {},
                "query_params": {},
                "body": {"name": "a" * 255, "email": "maxlength@example.com"},
                "expected_status": 201,
                "test_type": "boundary",
                "tags": ["users"]
            },
            {
                "test_id": 9,
                "name": "用户名最小长度",
                "description": "使用最小长度的用户名（1个字符）",
                "method": "POST",
                "path": "/users",
                "headers": {"Content-Type": "application/json"},
                "path_params": {},
                "query_params": {},
                "body": {"name": "a", "email": "minlength@example.com"},
                "expected_status": 201,
                "test_type": "boundary",
                "tags": ["users"]
            },
            {
                "test_id": 10,
                "name": "空字符串用户名",
                "description": "使用空字符串作为用户名",
                "method": "POST",
                "path": "/users",
                "headers": {"Content-Type": "application/json"},
                "path_params": {},
                "query_params": {},
                "body": {"name": "", "email": "empty@example.com"},
                "expected_status": 400,
                "test_type": "boundary",
                "tags": ["users"]
            }
        ]
        
        llm_response = LLMResponse(
            content=json.dumps(test_cases_json),
            model="gpt-3.5-turbo"
        )
        llm_client.generate.return_value = llm_response
        
        # Generate test cases
        collection = await generator.generate_test_cases(endpoint)
        
        # Verify collection
        assert collection.endpoint_id == "POST:/users"
        assert collection.method == "POST"
        assert collection.path == "/users"
        assert collection.summary == "Create user"
        assert len(collection.test_cases) == 10
        
        # Verify test case types
        positive_cases = [tc for tc in collection.test_cases if tc.test_type == TestType.POSITIVE]
        negative_cases = [tc for tc in collection.test_cases if tc.test_type == TestType.NEGATIVE]
        boundary_cases = [tc for tc in collection.test_cases if tc.test_type == TestType.BOUNDARY]
        
        assert len(positive_cases) == 3
        assert len(negative_cases) == 4
        assert len(boundary_cases) == 3
        
        # Verify LLM was called correctly
        llm_client.generate.assert_called_once()
        call_args = llm_client.generate.call_args
        assert "POST" in call_args.kwargs["prompt"]
        assert "/users" in call_args.kwargs["prompt"]
        assert call_args.kwargs["system_prompt"] is not None
    
    @pytest.mark.asyncio
    async def test_generate_test_cases_invalid_json(self):
        """Test generation with invalid JSON response."""
        llm_client = AsyncMock()
        generator = TestCaseGenerator(llm_client)
        
        endpoint = APIEndpoint(method="GET", path="/users")
        
        # Mock invalid JSON response
        llm_response = LLMResponse(
            content="invalid json response",
            model="gpt-3.5-turbo"
        )
        llm_client.generate.return_value = llm_response
        
        with pytest.raises(TestGeneratorError, match="Invalid JSON"):
            await generator.generate_test_cases(endpoint)
    
    @pytest.mark.asyncio
    async def test_generate_test_cases_non_array_response(self):
        """Test generation with non-array JSON response."""
        llm_client = AsyncMock()
        generator = TestCaseGenerator(llm_client)
        
        endpoint = APIEndpoint(method="GET", path="/users")
        
        # Mock non-array response
        llm_response = LLMResponse(
            content='{"message": "not an array"}',
            model="gpt-3.5-turbo"
        )
        llm_client.generate.return_value = llm_response
        
        with pytest.raises(TestGeneratorError, match="must be a JSON array"):
            await generator.generate_test_cases(endpoint)
    
    @pytest.mark.asyncio
    async def test_generate_test_cases_insufficient_positive(self):
        """Test generation with insufficient positive test cases."""
        llm_client = AsyncMock()
        generator = TestCaseGenerator(llm_client)
        
        endpoint = APIEndpoint(method="GET", path="/users")
        
        # Mock response with insufficient positive cases (only 1, need at least 2)
        test_cases_json = [
            {
                "test_id": 1,
                "name": "正向测试1",
                "description": "第一个正向测试用例（需要至少2个）",
                "method": "GET",
                "path": "/users",
                "headers": {},
                "path_params": {},
                "query_params": {},
                "body": None,
                "expected_status": 200,
                "test_type": "positive",
                "tags": []
            },
            {
                "test_id": 2,
                "name": "负向测试1",
                "description": "第一个负向测试用例",
                "method": "GET",
                "path": "/users",
                "headers": {},
                "path_params": {},
                "query_params": {"page": -1},
                "body": None,
                "expected_status": 400,
                "test_type": "negative",
                "tags": []
            },
            {
                "test_id": 3,
                "name": "负向测试2",
                "description": "第二个负向测试用例",
                "method": "GET",
                "path": "/users",
                "headers": {},
                "path_params": {},
                "query_params": {},
                "body": None,
                "expected_status": 401,
                "test_type": "negative",
                "tags": []
            },
            {
                "test_id": 4,
                "name": "负向测试3",
                "description": "第三个负向测试用例",
                "method": "GET",
                "path": "/users",
                "headers": {},
                "path_params": {},
                "query_params": {},
                "body": None,
                "expected_status": 403,
                "test_type": "negative",
                "tags": []
            },
            {
                "test_id": 5,
                "name": "负向测试4",
                "description": "第四个负向测试用例",
                "method": "GET",
                "path": "/users",
                "headers": {},
                "path_params": {},
                "query_params": {"invalid": "param"},
                "body": None,
                "expected_status": 400,
                "test_type": "negative",
                "tags": []
            }
        ]
        
        llm_response = LLMResponse(
            content=json.dumps(test_cases_json),
            model="gpt-3.5-turbo"
        )
        llm_client.generate.return_value = llm_response
        
        with pytest.raises(TestGeneratorError, match="At least 2 positive test cases"):
            await generator.generate_test_cases(endpoint)
    
    @pytest.mark.asyncio
    async def test_generate_test_cases_insufficient_negative(self):
        """Test generation with insufficient negative test cases."""
        llm_client = AsyncMock()
        generator = TestCaseGenerator(llm_client)
        
        endpoint = APIEndpoint(method="GET", path="/users")
        
        # Mock response with insufficient negative cases (only 1, need at least 2)
        test_cases_json = [
            {
                "test_id": 1,
                "name": "正向测试1",
                "description": "第一个正向测试用例",
                "method": "GET",
                "path": "/users",
                "headers": {},
                "path_params": {},
                "query_params": {},
                "body": None,
                "expected_status": 200,
                "test_type": "positive",
                "tags": []
            },
            {
                "test_id": 2,
                "name": "正向测试2",
                "description": "第二个正向测试用例",
                "method": "GET",
                "path": "/users",
                "headers": {},
                "path_params": {},
                "query_params": {"page": 1},
                "body": None,
                "expected_status": 200,
                "test_type": "positive",
                "tags": []
            },
            {
                "test_id": 3,
                "name": "负向测试1",
                "description": "第一个负向测试用例（需要至少2个）",
                "method": "GET", 
                "path": "/users",
                "headers": {},
                "path_params": {},
                "query_params": {"page": -1},
                "body": None,
                "expected_status": 400,
                "test_type": "negative",
                "tags": []
            }
        ]
        
        llm_response = LLMResponse(
            content=json.dumps(test_cases_json),
            model="gpt-3.5-turbo"
        )
        llm_client.generate.return_value = llm_response
        
        with pytest.raises(TestGeneratorError, match="At least 2 negative test cases"):
            await generator.generate_test_cases(endpoint)
    
    @pytest.mark.asyncio
    async def test_generate_test_cases_markdown_response(self):
        """Test generation with markdown-wrapped JSON response."""
        llm_client = AsyncMock()
        generator = TestCaseGenerator(llm_client)
        
        endpoint = APIEndpoint(method="GET", path="/users")
        
        # Mock response with markdown code blocks (10 test cases)
        test_cases_json = [
            # Positive test cases (3)
            {
                "test_id": 1,
                "name": "获取用户列表成功",
                "description": "成功获取用户列表",
                "method": "GET",
                "path": "/users",
                "headers": {"Accept": "application/json"},
                "path_params": {},
                "query_params": {},
                "body": None,
                "expected_status": 200,
                "test_type": "positive",
                "tags": []
            },
            {
                "test_id": 2,
                "name": "分页获取用户",
                "description": "使用分页参数获取用户列表",
                "method": "GET",
                "path": "/users",
                "headers": {"Accept": "application/json"},
                "path_params": {},
                "query_params": {"page": 1, "limit": 10},
                "body": None,
                "expected_status": 200,
                "test_type": "positive",
                "tags": []
            },
            {
                "test_id": 3,
                "name": "按条件筛选用户",
                "description": "根据状态筛选活跃用户",
                "method": "GET",
                "path": "/users",
                "headers": {"Accept": "application/json"},
                "path_params": {},
                "query_params": {"status": "active"},
                "body": None,
                "expected_status": 200,
                "test_type": "positive",
                "tags": []
            },
            # Negative test cases (4)
            {
                "test_id": 4,
                "name": "无效的分页参数",
                "description": "使用负数作为页码",
                "method": "GET",
                "path": "/users",
                "headers": {"Accept": "application/json"},
                "path_params": {},
                "query_params": {"page": -1},
                "body": None,
                "expected_status": 400,
                "test_type": "negative",
                "tags": []
            },
            {
                "test_id": 5,
                "name": "缺少认证头",
                "description": "请求未包含认证信息",
                "method": "GET",
                "path": "/users",
                "headers": {},
                "path_params": {},
                "query_params": {},
                "body": None,
                "expected_status": 401,
                "test_type": "negative",
                "tags": []
            },
            {
                "test_id": 6,
                "name": "权限不足", 
                "description": "普通用户尝试访问管理接口",
                "method": "GET",
                "path": "/users",
                "headers": {"Authorization": "Bearer user-token"},
                "path_params": {},
                "query_params": {},
                "body": None,
                "expected_status": 403,
                "test_type": "negative",
                "tags": []
            },
            {
                "test_id": 7,
                "name": "无效的筛选参数",
                "description": "使用不存在的状态值",
                "method": "GET",
                "path": "/users",
                "headers": {"Accept": "application/json"},
                "path_params": {},
                "query_params": {"status": "invalid-status"},
                "body": None,
                "expected_status": 400,
                "test_type": "negative",
                "tags": []
            },
            # Boundary test cases (3)
            {
                "test_id": 8,
                "name": "最大分页限制",
                "description": "请求每页最大允许数量",
                "method": "GET",
                "path": "/users",
                "headers": {"Accept": "application/json"},
                "path_params": {},
                "query_params": {"limit": 100},
                "body": None,
                "expected_status": 200,
                "test_type": "boundary",
                "tags": []
            },
            {
                "test_id": 9,
                "name": "超出最大分页限制",
                "description": "请求超过最大允许的每页数量",
                "method": "GET",
                "path": "/users",
                "headers": {"Accept": "application/json"},
                "path_params": {},
                "query_params": {"limit": 1000},
                "body": None,
                "expected_status": 400,
                "test_type": "boundary",
                "tags": []
            },
            {
                "test_id": 10,
                "name": "分页参数为零",
                "description": "使用0作为分页大小",
                "method": "GET",
                "path": "/users",
                "headers": {"Accept": "application/json"},
                "path_params": {},
                "query_params": {"limit": 0},
                "body": None,
                "expected_status": 400,
                "test_type": "boundary",
                "tags": []
            }
        ]
        
        markdown_content = f"```json\n{json.dumps(test_cases_json, indent=2)}\n```"
        
        llm_response = LLMResponse(
            content=markdown_content,
            model="gpt-3.5-turbo"
        )
        llm_client.generate.return_value = llm_response
        
        # Should successfully parse despite markdown wrapper
        collection = await generator.generate_test_cases(endpoint)
        assert len(collection.test_cases) == 10
    
    def test_get_system_prompt(self):
        """Test system prompt generation."""
        llm_client = Mock()
        generator = TestCaseGenerator(llm_client)
        
        system_prompt = generator._get_system_prompt()
        
        assert "你是一个API用例设计测试专家" in system_prompt
        assert "测试用例要求" in system_prompt
        assert "负向测试的Headers策略" in system_prompt
        assert "JSON" in system_prompt
        assert "expected_response_headers" in system_prompt
        assert "expected_response_content" in system_prompt
        assert "business_rules" in system_prompt
        assert "完整的预期验证信息" in system_prompt
        assert "test_id" in system_prompt
    
    def test_build_prompt(self):
        """Test prompt building."""
        llm_client = Mock()
        generator = TestCaseGenerator(llm_client)
        
        endpoint = APIEndpoint(
            method="POST",
            path="/users/{id}",
            summary="Update user",
            description="Update an existing user",
            tags=["users"],
            parameters=[
                APIParameter(
                    name="id",
                    location="path",
                    type="integer",
                    required=True,
                    description="User ID"
                )
            ]
        )
        
        prompt = generator._build_prompt(endpoint)
        
        assert "POST" in prompt
        assert "/users/{id}" in prompt
        assert "Update user" in prompt
        assert "User ID" in prompt
        assert "JSON Schema" in prompt
    
    def test_get_test_case_schema(self):
        """Test test case schema generation."""
        llm_client = Mock()
        generator = TestCaseGenerator(llm_client)
        
        schema = generator._get_test_case_schema()
        
        assert schema["type"] == "object"
        assert "test_id" in schema["required"]
        assert "name" in schema["required"]
        assert "description" in schema["required"]
        assert "method" in schema["required"]
        assert "path" in schema["required"]
        assert "expected_status" in schema["required"]
        assert "test_type" in schema["required"]
        
        # Check test_type enum values
        test_type_prop = schema["properties"]["test_type"]
        assert test_type_prop["enum"] == ["positive", "negative", "boundary"]
        
        # Check test_id property
        test_id_prop = schema["properties"]["test_id"]
        assert test_id_prop["type"] == "integer"
        assert test_id_prop["minimum"] == 1
    
    @pytest.mark.asyncio
    async def test_metadata_setting(self):
        """Test that metadata is properly set with API version and LLM model."""
        llm_client = AsyncMock()
        generator = TestCaseGenerator(llm_client, api_version="2.0.0")
        
        endpoint = APIEndpoint(method="GET", path="/health")
        
        # Mock LLM response with proper test coverage (10 test cases)
        test_cases_json = [
            # Positive test cases (3)
            {
                "test_id": 1,
                "name": "健康检查成功",
                "description": "测试健康检查接口返回正常状态",
                "method": "GET",
                "path": "/health",
                "headers": {"Accept": "application/json"},
                "path_params": {},
                "query_params": {},
                "body": None,
                "expected_status": 200,
                "test_type": "positive",
                "tags": ["health"]
            },
            {
                "test_id": 2,
                "name": "带认证的健康检查",
                "description": "使用有效认证令牌进行健康检查",
                "method": "GET",
                "path": "/health",
                "headers": {"Accept": "application/json", "Authorization": "Bearer valid-token"},
                "path_params": {},
                "query_params": {},
                "body": None,
                "expected_status": 200,
                "test_type": "positive",
                "tags": ["health"]
            },
            {
                "test_id": 3,
                "name": "详细健康检查",
                "description": "获取详细的健康状态信息",
                "method": "GET",
                "path": "/health",
                "headers": {"Accept": "application/json"},
                "path_params": {},
                "query_params": {"detailed": "true"},
                "body": None,
                "expected_status": 200,
                "test_type": "positive",
                "tags": ["health"]
            },
            # Negative test cases (4)
            {
                "test_id": 4,
                "name": "健康检查使用错误方法",
                "description": "使用POST方法访问健康检查接口应返回405",
                "method": "GET",
                "path": "/health",
                "headers": {},
                "path_params": {},
                "query_params": {},
                "body": None,
                "expected_status": 405,
                "test_type": "negative",
                "tags": ["health"]
            },
            {
                "test_id": 5,
                "name": "健康检查带无效查询参数",
                "description": "带有无效查询参数的健康检查",
                "method": "GET",
                "path": "/health",
                "headers": {"Accept": "application/json"},
                "path_params": {},
                "query_params": {"invalid": "param"},
                "body": None,
                "expected_status": 400,
                "test_type": "negative",
                "tags": ["health"]
            },
            {
                "test_id": 6,
                "name": "健康检查错误路径",
                "description": "访问不存在的健康检查路径",
                "method": "GET",
                "path": "/health",
                "headers": {},
                "path_params": {},
                "query_params": {},
                "body": None,
                "expected_status": 404,
                "test_type": "negative",
                "tags": ["health"]
            },
            {
                "test_id": 7,
                "name": "无效的认证令牌",
                "description": "使用无效的认证令牌访问健康检查",
                "method": "GET",
                "path": "/health",
                "headers": {"Authorization": "Bearer invalid-token"},
                "path_params": {},
                "query_params": {},
                "body": None,
                "expected_status": 401,
                "test_type": "negative",
                "tags": ["health"]
            },
            # Boundary test cases (3)
            {
                "test_id": 8,
                "name": "超长查询参数",
                "description": "使用超长查询参数进行健康检查",
                "method": "GET",
                "path": "/health",
                "headers": {"Accept": "application/json"},
                "path_params": {},
                "query_params": {"longparam": "x" * 1000},
                "body": None,
                "expected_status": 414,
                "test_type": "boundary",
                "tags": ["health"]
            },
            {
                "test_id": 9,
                "name": "空查询参数",
                "description": "使用空查询参数进行健康检查",
                "method": "GET",
                "path": "/health",
                "headers": {"Accept": "application/json"},
                "path_params": {},
                "query_params": {"": ""},
                "body": None,
                "expected_status": 400,
                "test_type": "boundary",
                "tags": ["health"]
            },
            {
                "test_id": 10,
                "name": "特殊字符查询参数",
                "description": "使用特殊字符作为查询参数",
                "method": "GET",
                "path": "/health",
                "headers": {"Accept": "application/json"},
                "path_params": {},
                "query_params": {"param": "!@#$%^&*()"},
                "body": None,
                "expected_status": 400,
                "test_type": "boundary",
                "tags": ["health"]
            }
        ]
        
        llm_response = LLMResponse(
            content=json.dumps(test_cases_json),
            model="glm-4.5-x"
        )
        llm_client.generate.return_value = llm_response
        
        # Generate test cases
        collection = await generator.generate_test_cases(endpoint)
        
        # Verify metadata
        assert len(collection.test_cases) == 10
        
        # Check Chinese names and descriptions
        test_case = collection.test_cases[0]
        assert test_case.name == "健康检查成功"
        assert "测试健康检查" in test_case.description
        
        # Check metadata for all test cases
        for test_case in collection.test_cases:
            assert test_case.metadata.api_version == "2.0.0"
            assert test_case.metadata.llm_model == "glm-4.5-x"
            assert test_case.metadata.generated_at is not None
    
    def test_expected_response_schema_never_null(self):
        """Test that expected_response_schema is never null."""
        llm_client = Mock()
        generator = TestCaseGenerator(llm_client)
        
        # Test default schema generation
        schema_200 = generator._get_default_response_schema("200")
        assert schema_200 is not None
        assert schema_200["type"] == "object"
        assert schema_200["additionalProperties"] == True
        
        schema_400 = generator._get_default_response_schema("400")
        assert schema_400 is not None
        assert "error" in schema_400["properties"]
        
        schema_500 = generator._get_default_response_schema("500")
        assert schema_500 is not None
        assert "error" in schema_500["properties"]