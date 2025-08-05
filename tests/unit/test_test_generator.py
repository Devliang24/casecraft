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
        
        # Mock LLM response with valid test cases
        test_cases_json = [
            {
                "name": "Create user with valid data",
                "description": "Test successful user creation with all required fields",
                "method": "POST",
                "path": "/users",
                "headers": {"Content-Type": "application/json"},
                "path_params": {},
                "query_params": {},
                "body": {"name": "John Doe", "email": "john@example.com"},
                "expected_status": 201,
                "test_type": "positive",
                "tags": ["users"]
            },
            {
                "name": "Create user without required field",
                "description": "Test user creation failure when name is missing",
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
                "name": "Create user with invalid email",
                "description": "Test user creation failure with invalid email format",
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
                "name": "Create user with empty body",
                "description": "Test user creation failure with empty request body",
                "method": "POST",
                "path": "/users",
                "headers": {"Content-Type": "application/json"},
                "path_params": {},
                "query_params": {},
                "body": {},
                "expected_status": 400,
                "test_type": "negative",
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
        assert len(collection.test_cases) == 4
        
        # Verify test case types
        positive_cases = [tc for tc in collection.test_cases if tc.test_type == TestType.POSITIVE]
        negative_cases = [tc for tc in collection.test_cases if tc.test_type == TestType.NEGATIVE]
        
        assert len(positive_cases) == 1
        assert len(negative_cases) == 3
        
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
        
        # Mock response with only negative cases
        test_cases_json = [
            {
                "name": "Test negative case",
                "description": "A negative test case",
                "method": "GET",
                "path": "/users",
                "headers": {},
                "path_params": {},
                "query_params": {},
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
        
        with pytest.raises(TestGeneratorError, match="At least 1 positive test case"):
            await generator.generate_test_cases(endpoint)
    
    @pytest.mark.asyncio
    async def test_generate_test_cases_insufficient_negative(self):
        """Test generation with insufficient negative test cases."""
        llm_client = AsyncMock()
        generator = TestCaseGenerator(llm_client)
        
        endpoint = APIEndpoint(method="GET", path="/users")
        
        # Mock response with insufficient negative cases
        test_cases_json = [
            {
                "name": "Test positive case",
                "description": "A positive test case",
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
                "name": "Test negative case",
                "description": "A negative test case",
                "method": "GET", 
                "path": "/users",
                "headers": {},
                "path_params": {},
                "query_params": {},
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
        
        with pytest.raises(TestGeneratorError, match="At least 3 negative test cases"):
            await generator.generate_test_cases(endpoint)
    
    @pytest.mark.asyncio
    async def test_generate_test_cases_markdown_response(self):
        """Test generation with markdown-wrapped JSON response."""
        llm_client = AsyncMock()
        generator = TestCaseGenerator(llm_client)
        
        endpoint = APIEndpoint(method="GET", path="/users")
        
        # Mock response with markdown code blocks
        test_cases_json = [
            {
                "name": "Test case",
                "description": "A test case",
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
                "name": "Negative test 1",
                "description": "Negative test case 1",
                "method": "GET",
                "path": "/users",
                "headers": {},
                "path_params": {},
                "query_params": {},
                "body": None,
                "expected_status": 400,
                "test_type": "negative",
                "tags": []
            },
            {
                "name": "Negative test 2", 
                "description": "Negative test case 2",
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
                "name": "Negative test 3",
                "description": "Negative test case 3",
                "method": "GET",
                "path": "/users",
                "headers": {},
                "path_params": {},
                "query_params": {},
                "body": None,
                "expected_status": 403,
                "test_type": "negative",
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
        assert len(collection.test_cases) == 4
    
    def test_get_system_prompt(self):
        """Test system prompt generation."""
        llm_client = Mock()
        generator = TestCaseGenerator(llm_client)
        
        system_prompt = generator._get_system_prompt()
        
        assert "expert API testing specialist" in system_prompt
        assert "Positive Cases" in system_prompt
        assert "Negative Cases" in system_prompt
        assert "Boundary Cases" in system_prompt
        assert "JSON array" in system_prompt
    
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
        assert "name" in schema["required"]
        assert "description" in schema["required"]
        assert "method" in schema["required"]
        assert "path" in schema["required"]
        assert "expected_status" in schema["required"]
        assert "test_type" in schema["required"]
        
        # Check test_type enum values
        test_type_prop = schema["properties"]["test_type"]
        assert test_type_prop["enum"] == ["positive", "negative", "boundary"]
    
    @pytest.mark.asyncio
    async def test_metadata_setting(self):
        """Test that metadata is properly set with API version and LLM model."""
        llm_client = AsyncMock()
        generator = TestCaseGenerator(llm_client, api_version="2.0.0")
        
        endpoint = APIEndpoint(method="GET", path="/health")
        
        # Mock LLM response with proper test coverage
        test_cases_json = [
            {
                "name": "健康检查成功",
                "description": "测试健康检查接口返回正常状态",
                "method": "GET",
                "path": "/health",
                "headers": {},
                "path_params": {},
                "query_params": {},
                "body": None,
                "expected_status": 200,
                "test_type": "positive",
                "tags": ["health"]
            },
            {
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
                "name": "健康检查带无效查询参数",
                "description": "带有无效查询参数的健康检查",
                "method": "GET",
                "path": "/health",
                "headers": {},
                "path_params": {},
                "query_params": {"invalid": "param"},
                "body": None,
                "expected_status": 400,
                "test_type": "negative",
                "tags": ["health"]
            },
            {
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
        assert len(collection.test_cases) == 4
        
        # Check Chinese names and descriptions
        test_case = collection.test_cases[0]
        assert test_case.name == "健康检查成功"
        assert "测试健康检查" in test_case.description
        
        # Check metadata for all test cases
        for test_case in collection.test_cases:
            assert test_case.metadata.api_version == "2.0.0"
            assert test_case.metadata.llm_model == "glm-4.5-x"
            assert test_case.metadata.generated_at is not None