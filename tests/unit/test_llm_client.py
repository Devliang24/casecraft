"""Tests for LLM client implementation."""

import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
import httpx

from casecraft.core.generation.llm_client import (
    LLMClient, create_llm_client, LLMError, LLMRateLimitError, LLMResponse
)
from casecraft.models.config import LLMConfig


class TestLLMResponse:
    """Test LLM response model."""
    
    def test_llm_response_creation(self):
        """Test LLM response creation."""
        response = LLMResponse(
            content="Test response",
            model="glm-4.5-x",
            usage={"total_tokens": 100},
            finish_reason="stop"
        )
        
        assert response.content == "Test response"
        assert response.model == "glm-4.5-x"
        assert response.usage["total_tokens"] == 100
        assert response.finish_reason == "stop"
    
    def test_llm_response_minimal(self):
        """Test LLM response with minimal data."""
        response = LLMResponse(
            content="Test",
            model="glm-4.5-x"
        )
        
        assert response.content == "Test"
        assert response.model == "glm-4.5-x"
        assert response.usage is None
        assert response.finish_reason is None


class TestLLMClient:
    """Test LLM client implementation."""
    
    def test_init(self):
        """Test client initialization."""
        config = LLMConfig(
            model="glm-4.5-x",
            api_key="test-key"
        )
        
        client = LLMClient(config)
        assert client.config == config
        assert client.base_url == "https://open.bigmodel.cn/api/paas/v4"
    
    def test_init_custom_base_url(self):
        """Test client with custom base URL."""
        config = LLMConfig(
            model="glm-4.5-x",
            api_key="test-key",
            base_url="https://custom.bigmodel.cn/api/v4"
        )
        
        client = LLMClient(config)
        assert client.base_url == "https://custom.bigmodel.cn/api/v4"
    
    @pytest.mark.asyncio
    async def test_generate_success(self):
        """Test successful generation."""
        config = LLMConfig(
            model="glm-4.5-x",
            api_key="test-key"
        )
        
        client = LLMClient(config)
        
        # Mock response
        mock_response = {
            "choices": [{
                "message": {"content": "Generated test cases"},
                "finish_reason": "stop"
            }],
            "model": "glm-4.5-x",
            "usage": {"total_tokens": 150}
        }
        
        with patch.object(client, '_make_request_with_retry', return_value=mock_response):
            response = await client.generate("Generate test cases")
            
            assert response.content == "Generated test cases"
            assert response.model == "glm-4.5-x"
            assert response.usage["total_tokens"] == 150
            assert response.finish_reason == "stop"
    
    @pytest.mark.asyncio
    async def test_generate_with_system_prompt(self):
        """Test generation with system prompt."""
        config = LLMConfig(
            model="glm-4.5-x",
            api_key="test-key"
        )
        
        client = LLMClient(config)
        
        mock_response = {
            "choices": [{
                "message": {"content": "Response with system"},
                "finish_reason": "stop"
            }],
            "model": "glm-4.5-x"
        }
        
        with patch.object(client, '_make_request_with_retry', return_value=mock_response) as mock_request:
            response = await client.generate(
                "User prompt",
                system_prompt="System prompt"
            )
            
            # Verify the request payload
            call_args = mock_request.call_args[0]
            payload = call_args[1]
            
            assert len(payload["messages"]) == 2
            assert payload["messages"][0]["role"] == "system"
            assert payload["messages"][0]["content"] == "System prompt"
            assert payload["messages"][1]["role"] == "user"
            assert payload["messages"][1]["content"] == "User prompt"
    
    @pytest.mark.asyncio
    async def test_generate_error(self):
        """Test generation error handling."""
        config = LLMConfig(
            model="glm-4.5-x",
            api_key="test-key"
        )
        
        client = LLMClient(config)
        
        with patch.object(client, '_make_request_with_retry', side_effect=Exception("API error")):
            with pytest.raises(LLMError, match="BigModel API error"):
                await client.generate("Generate test cases")
    
    @pytest.mark.asyncio
    async def test_rate_limit_handling(self):
        """Test rate limit error handling."""
        config = LLMConfig(
            model="glm-4.5-x",
            api_key="test-key",
            max_retries=2
        )
        
        client = LLMClient(config)
        
        # Mock HTTP client with 429 response
        mock_response = httpx.Response(
            status_code=429,
            headers={"retry-after": "1"}
        )
        
        with patch.object(client.client, 'post', return_value=mock_response):
            with pytest.raises(LLMRateLimitError):
                await client._make_request_with_retry("/chat/completions", {})
    
    @pytest.mark.asyncio
    async def test_server_error_retry(self):
        """Test retry on server errors."""
        config = LLMConfig(
            model="glm-4.5-x",
            api_key="test-key",
            max_retries=2
        )
        
        client = LLMClient(config)
        
        # First two calls fail with 500, third succeeds
        responses = [
            httpx.Response(status_code=500),
            httpx.Response(status_code=500),
            httpx.Response(
                status_code=200,
                json={"choices": [{"message": {"content": "Success"}}]}
            )
        ]
        
        with patch.object(client.client, 'post', side_effect=responses):
            # Use a smaller sleep time for testing
            with patch('asyncio.sleep', return_value=None):
                result = await client._make_request_with_retry("/chat/completions", {})
                assert result["choices"][0]["message"]["content"] == "Success"
    
    @pytest.mark.asyncio
    async def test_close(self):
        """Test client cleanup."""
        config = LLMConfig(
            model="glm-4.5-x",
            api_key="test-key"
        )
        
        client = LLMClient(config)
        
        with patch.object(client.client, 'aclose', new_callable=AsyncMock) as mock_close:
            await client.close()
            mock_close.assert_called_once()


class TestCreateLLMClient:
    """Test LLM client factory function."""
    
    def test_create_llm_client(self):
        """Test creating LLM client."""
        config = LLMConfig(
            model="glm-4.5-x",
            api_key="test-key"
        )
        
        client = create_llm_client(config)
        assert isinstance(client, LLMClient)
        assert client.config == config