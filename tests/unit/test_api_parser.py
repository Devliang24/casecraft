"""Tests for API documentation parser."""

import json
import pytest
from unittest.mock import AsyncMock, patch

from casecraft.core.parsing.api_parser import APIParser, APIParseError
from casecraft.models.api_spec import APISpecification, APIEndpoint


class TestAPIParser:
    """Test API parser functionality."""
    
    def test_init(self):
        """Test parser initialization."""
        parser = APIParser()
        assert parser.timeout == 30
        
        parser = APIParser(timeout=60)
        assert parser.timeout == 60
    
    def test_is_url(self):
        """Test URL detection."""
        parser = APIParser()
        
        assert parser._is_url("https://example.com/api.json")
        assert parser._is_url("http://localhost:8080/openapi.yaml")
        assert not parser._is_url("/path/to/file.json")
        assert not parser._is_url("file.yaml")
        assert not parser._is_url("invalid-url")
    
    def test_get_content_hash(self):
        """Test content hashing."""
        parser = APIParser()
        
        content1 = "test content"
        content2 = "test content"
        content3 = "different content"
        
        hash1 = parser.get_content_hash(content1)
        hash2 = parser.get_content_hash(content2)
        hash3 = parser.get_content_hash(content3)
        
        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 32  # MD5 hash length
    
    def test_parse_openapi_v3_basic(self, sample_openapi_spec):
        """Test basic OpenAPI 3.0 parsing."""
        parser = APIParser()
        content = json.dumps(sample_openapi_spec)
        
        spec = parser.parse_from_content(content, "test.json")
        
        assert isinstance(spec, APISpecification)
        assert spec.title == "Sample API"
        assert spec.version == "1.0.0"
        assert spec.description == "A sample API for testing"
        assert len(spec.endpoints) == 3  # GET/POST /users, GET /users/{id}
    
    def test_parse_openapi_v3_endpoints(self, sample_openapi_spec):
        """Test OpenAPI 3.0 endpoint parsing."""
        parser = APIParser()
        content = json.dumps(sample_openapi_spec)
        
        spec = parser.parse_from_content(content, "test.json")
        
        # Check GET /users endpoint
        get_users = next((ep for ep in spec.endpoints 
                         if ep.method == "GET" and ep.path == "/users"), None)
        assert get_users is not None
        assert get_users.summary == "List users"
        assert "users" in get_users.tags
        assert "200" in get_users.responses
        
        # Check POST /users endpoint
        post_users = next((ep for ep in spec.endpoints 
                          if ep.method == "POST" and ep.path == "/users"), None)
        assert post_users is not None
        assert post_users.summary == "Create user"
        assert post_users.request_body is not None
        assert "201" in post_users.responses
        
        # Check GET /users/{id} endpoint
        get_user = next((ep for ep in spec.endpoints 
                        if ep.method == "GET" and ep.path == "/users/{id}"), None)
        assert get_user is not None
        assert len(get_user.parameters) == 1
        assert get_user.parameters[0].name == "id"
        assert get_user.parameters[0].location == "path"
        assert get_user.parameters[0].required is True
    
    def test_parse_swagger_v2(self):
        """Test Swagger 2.0 parsing."""
        swagger_spec = {
            "swagger": "2.0",
            "info": {
                "title": "Swagger API",
                "version": "2.0.0"
            },
            "host": "api.example.com",
            "basePath": "/v2",
            "schemes": ["https"],
            "paths": {
                "/pets": {
                    "get": {
                        "summary": "List pets",
                        "tags": ["pets"],
                        "parameters": [
                            {
                                "name": "limit",
                                "in": "query",
                                "type": "integer",
                                "required": False
                            }
                        ],
                        "responses": {
                            "200": {
                                "description": "List of pets"
                            }
                        }
                    },
                    "post": {
                        "summary": "Create pet",
                        "tags": ["pets"],
                        "parameters": [
                            {
                                "name": "pet",
                                "in": "body",
                                "required": True,
                                "schema": {
                                    "$ref": "#/definitions/Pet"
                                }
                            }
                        ],
                        "responses": {
                            "201": {
                                "description": "Pet created"
                            }
                        }
                    }
                }
            },
            "definitions": {
                "Pet": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "status": {"type": "string"}
                    }
                }
            }
        }
        
        parser = APIParser()
        content = json.dumps(swagger_spec)
        
        spec = parser.parse_from_content(content, "swagger.json")
        
        assert spec.title == "Swagger API"
        assert spec.version == "2.0.0"
        assert spec.base_url == "https://api.example.com/v2"
        assert len(spec.endpoints) == 2
        
        # Check POST endpoint with body parameter
        post_pets = next((ep for ep in spec.endpoints 
                         if ep.method == "POST"), None)
        assert post_pets is not None
        assert post_pets.request_body is not None
        assert post_pets.request_body["required"] is True
    
    def test_parse_invalid_json(self):
        """Test parsing invalid JSON."""
        parser = APIParser()
        invalid_content = "{ invalid json content"
        
        with pytest.raises(APIParseError, match="Invalid JSON/YAML"):
            parser.parse_from_content(invalid_content, "invalid.json")
    
    def test_parse_invalid_yaml(self):
        """Test parsing invalid YAML."""
        parser = APIParser()
        invalid_content = "invalid: yaml: content: ["
        
        with pytest.raises(APIParseError, match="Invalid JSON/YAML"):
            parser.parse_from_content(invalid_content, "invalid.yaml")
    
    def test_parse_unsupported_format(self):
        """Test parsing unsupported format."""
        parser = APIParser()
        content = json.dumps({"title": "API", "version": "1.0"})  # No openapi/swagger field
        
        with pytest.raises(APIParseError, match="Unsupported API documentation format"):
            parser.parse_from_content(content, "unsupported.json")
    
    def test_parse_non_object_content(self):
        """Test parsing non-object content."""
        parser = APIParser()
        content = json.dumps(["array", "content"])
        
        with pytest.raises(APIParseError, match="must be a JSON/YAML object"):
            parser.parse_from_content(content, "array.json")
    
    @pytest.mark.asyncio
    async def test_read_from_file(self, tmp_path, sample_openapi_spec):
        """Test reading from file."""
        parser = APIParser()
        
        # Create test file
        file_path = tmp_path / "openapi.json"
        file_path.write_text(json.dumps(sample_openapi_spec))
        
        content = await parser._read_from_file(str(file_path))
        assert json.loads(content) == sample_openapi_spec
    
    @pytest.mark.asyncio
    async def test_read_from_nonexistent_file(self):
        """Test reading from non-existent file."""
        parser = APIParser()
        
        with pytest.raises(APIParseError, match="File not found"):
            await parser._read_from_file("/nonexistent/file.json")
    
    @pytest.mark.asyncio
    async def test_fetch_from_url_success(self, sample_openapi_spec):
        """Test successful URL fetching."""
        parser = APIParser()
        
        # Mock HTTP response
        mock_response = AsyncMock()
        mock_response.text = json.dumps(sample_openapi_spec)
        mock_response.raise_for_status = AsyncMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            content = await parser._fetch_from_url("https://example.com/api.json")
            assert json.loads(content) == sample_openapi_spec
    
    @pytest.mark.asyncio
    async def test_fetch_from_url_http_error(self):
        """Test URL fetching with HTTP error."""
        parser = APIParser()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = Exception("HTTP Error")
            
            with pytest.raises(APIParseError, match="Unexpected error fetching"):
                await parser._fetch_from_url("https://example.com/api.json")
    
    def test_filter_endpoints_by_tags(self, sample_openapi_spec):
        """Test endpoint filtering by tags."""
        parser = APIParser()
        content = json.dumps(sample_openapi_spec)
        spec = parser.parse_from_content(content, "test.json")
        
        # Filter to include only 'users' tag
        filtered = parser.filter_endpoints(spec, include_tags=["users"])
        assert len(filtered.endpoints) == 3  # All endpoints have 'users' tag
        
        # Filter to exclude 'users' tag
        filtered = parser.filter_endpoints(spec, exclude_tags=["users"])
        assert len(filtered.endpoints) == 0  # All endpoints have 'users' tag
        
        # Filter with non-existent tag
        filtered = parser.filter_endpoints(spec, include_tags=["nonexistent"])
        assert len(filtered.endpoints) == 0
    
    def test_filter_endpoints_by_paths(self, sample_openapi_spec):
        """Test endpoint filtering by path patterns."""
        parser = APIParser()
        content = json.dumps(sample_openapi_spec)
        spec = parser.parse_from_content(content, "test.json")
        
        # Filter to include specific path
        filtered = parser.filter_endpoints(spec, include_paths=["/users"])
        assert len(filtered.endpoints) == 2  # GET and POST /users
        
        # Filter with wildcard pattern
        filtered = parser.filter_endpoints(spec, include_paths=["/users/*"])
        assert len(filtered.endpoints) == 1  # GET /users/{id}
        
        # Filter to exclude pattern
        filtered = parser.filter_endpoints(spec, exclude_paths=["/users/{id}"])
        assert len(filtered.endpoints) == 2  # GET and POST /users
    
    def test_resolve_reference(self):
        """Test JSON reference resolution."""
        parser = APIParser()
        
        spec_data = {
            "components": {
                "schemas": {
                    "User": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"}
                        }
                    }
                }
            }
        }
        
        resolved = parser._resolve_reference("#/components/schemas/User", spec_data)
        assert resolved["type"] == "object"
        assert "name" in resolved["properties"]
        
        # Test invalid reference
        resolved = parser._resolve_reference("#/invalid/path", spec_data)
        assert resolved == {}
    
    def test_extract_parameter_type(self):
        """Test parameter type extraction."""
        parser = APIParser()
        
        # Parameter with schema
        param_with_schema = {
            "name": "id",
            "schema": {"type": "integer"}
        }
        assert parser._extract_parameter_type(param_with_schema) == "integer"
        
        # Parameter with direct type
        param_with_type = {
            "name": "name",
            "type": "string"
        }
        assert parser._extract_parameter_type(param_with_type) == "string"
        
        # Parameter with no type info
        param_no_type = {"name": "unknown"}
        assert parser._extract_parameter_type(param_no_type) == "string"