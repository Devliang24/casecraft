"""Tests for headers generation functionality."""

import pytest
from unittest.mock import Mock

from casecraft.core.parsing.headers_analyzer import HeadersAnalyzer, AuthType, ContentType
from casecraft.models.api_spec import APIEndpoint, APIParameter


class TestHeadersAnalyzer:
    """Test headers analyzer functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.analyzer = HeadersAnalyzer()
    
    def test_get_base_headers_get_request(self):
        """Test base headers for GET request."""
        endpoint = APIEndpoint(
            method="GET",
            path="/api/v1/users",
            operation_id="getUsers",
            summary="Get users",
            parameters=[]
        )
        
        headers = self.analyzer._get_base_headers(endpoint)
        
        assert headers == {"Accept": "application/json"}
    
    def test_get_base_headers_post_request(self):
        """Test base headers for POST request with body."""
        endpoint = APIEndpoint(
            method="POST",
            path="/api/v1/users",
            operation_id="createUser",
            summary="Create user",
            parameters=[
                APIParameter(
                    name="user",
                    location="body",
                    type="object",
                    required=True
                )
            ]
        )
        
        headers = self.analyzer._get_base_headers(endpoint)
        
        expected = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        assert headers == expected
    
    def test_infer_content_type_json(self):
        """Test content type inference for JSON."""
        endpoint = APIEndpoint(
            method="POST",
            path="/api/v1/users",
            operation_id="createUser",
            summary="Create user",
            parameters=[
                APIParameter(
                    name="user",
                    location="body",
                    type="object",
                    required=True
                )
            ]
        )
        
        content_type = self.analyzer._infer_content_type(endpoint)
        assert content_type == ContentType.JSON
    
    def test_infer_content_type_multipart(self):
        """Test content type inference for file upload."""
        endpoint = APIEndpoint(
            method="POST",
            path="/api/v1/upload",
            operation_id="uploadFile",
            summary="Upload file",
            parameters=[
                APIParameter(
                    name="file",
                    location="body",
                    type="file",
                    required=True
                )
            ]
        )
        
        content_type = self.analyzer._infer_content_type(endpoint)
        assert content_type == ContentType.MULTIPART
    
    def test_detect_auth_type_bearer_token(self):
        """Test bearer token authentication detection."""
        spec_data = {
            "components": {
                "securitySchemes": {
                    "bearerAuth": {
                        "type": "http",
                        "scheme": "bearer"
                    }
                }
            }
        }
        
        auth_type = self.analyzer._detect_auth_type(spec_data)
        assert auth_type == AuthType.BEARER_TOKEN
    
    def test_detect_auth_type_api_key(self):
        """Test API key authentication detection."""
        spec_data = {
            "components": {
                "securitySchemes": {
                    "apiKeyAuth": {
                        "type": "apiKey",
                        "in": "header",
                        "name": "X-API-Key"
                    }
                }
            }
        }
        
        auth_type = self.analyzer._detect_auth_type(spec_data)
        assert auth_type == AuthType.API_KEY
    
    def test_detect_auth_type_swagger_2(self):
        """Test authentication detection for Swagger 2.0."""
        spec_data = {
            "securityDefinitions": {
                "oauth2": {
                    "type": "oauth2",
                    "authorizationUrl": "https://example.com/oauth/authorize",
                    "flow": "implicit"
                }
            }
        }
        
        auth_type = self.analyzer._detect_auth_type(spec_data)
        assert auth_type == AuthType.OAUTH2
    
    def test_get_api_key_headers(self):
        """Test API key headers generation."""
        spec_data = {
            "components": {
                "securitySchemes": {
                    "apiKeyAuth": {
                        "type": "apiKey",
                        "in": "header",
                        "name": "X-API-Key"
                    }
                }
            }
        }
        
        headers = self.analyzer._get_api_key_headers(spec_data)
        assert headers == {"X-API-Key": "<valid-api-key>"}
    
    def test_get_api_key_headers_custom_name(self):
        """Test API key headers with custom header name."""
        spec_data = {
            "components": {
                "securitySchemes": {
                    "customAuth": {
                        "type": "apiKey",
                        "in": "header",
                        "name": "Authorization"
                    }
                }
            }
        }
        
        headers = self.analyzer._get_api_key_headers(spec_data)
        assert headers == {"Authorization": "<valid-api-key>"}
    
    def test_analyze_headers_no_auth(self):
        """Test headers analysis for endpoint without authentication."""
        endpoint = APIEndpoint(
            method="GET",
            path="/api/v1/public",
            operation_id="getPublicData",
            summary="Get public data",
            parameters=[]
        )
        
        scenarios = self.analyzer.analyze_headers(endpoint)
        
        assert "positive" in scenarios
        assert scenarios["positive"] == {"Accept": "application/json"}
    
    def test_analyze_headers_with_auth(self):
        """Test headers analysis for endpoint with authentication."""
        endpoint = APIEndpoint(
            method="POST",
            path="/api/v1/users",
            operation_id="createUser",
            summary="Create user",
            parameters=[
                APIParameter(
                    name="user",
                    location="body",
                    type="object",
                    required=True
                )
            ]
        )
        
        spec_data = {
            "components": {
                "securitySchemes": {
                    "bearerAuth": {
                        "type": "http",
                        "scheme": "bearer"
                    }
                }
            },
            "security": [{"bearerAuth": []}]
        }
        
        scenarios = self.analyzer.analyze_headers(endpoint, spec_data)
        
        expected_positive = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer <valid-token>"
        }
        
        assert scenarios["positive"] == expected_positive
        assert "negative_auth_missing" in scenarios
        assert "negative_auth_invalid" in scenarios
    
    def test_generate_negative_headers_auth_missing(self):
        """Test negative headers generation for missing authentication."""
        endpoint = APIEndpoint(
            method="GET",
            path="/api/v1/private",
            operation_id="getPrivateData",
            summary="Get private data",
            parameters=[]
        )
        
        positive_headers = {
            "Accept": "application/json",
            "Authorization": "Bearer <valid-token>"
        }
        
        spec_data = {
            "security": [{"bearerAuth": []}]
        }
        
        negative_scenarios = self.analyzer._generate_negative_headers(
            endpoint, positive_headers, spec_data
        )
        
        assert "negative_auth_missing" in negative_scenarios
        assert negative_scenarios["negative_auth_missing"] == {"Accept": "application/json"}
    
    def test_generate_negative_headers_invalid_auth(self):
        """Test negative headers generation for invalid authentication."""
        endpoint = APIEndpoint(
            method="GET",
            path="/api/v1/private",
            operation_id="getPrivateData",
            summary="Get private data",
            parameters=[]
        )
        
        positive_headers = {
            "Accept": "application/json",
            "Authorization": "Bearer <valid-token>"
        }
        
        spec_data = {
            "security": [{"bearerAuth": []}]
        }
        
        negative_scenarios = self.analyzer._generate_negative_headers(
            endpoint, positive_headers, spec_data
        )
        
        assert "negative_auth_invalid" in negative_scenarios
        assert negative_scenarios["negative_auth_invalid"]["Authorization"] == "Bearer invalid-token"
    
    def test_generate_negative_headers_content_type(self):
        """Test negative headers generation for wrong content type."""
        endpoint = APIEndpoint(
            method="POST",
            path="/api/v1/users",
            operation_id="createUser",
            summary="Create user",
            parameters=[
                APIParameter(
                    name="user",
                    location="body",
                    type="object",
                    required=True
                )
            ]
        )
        
        positive_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        negative_scenarios = self.analyzer._generate_negative_headers(
            endpoint, positive_headers, None
        )
        
        assert "negative_content_type" in negative_scenarios
        assert negative_scenarios["negative_content_type"]["Content-Type"] == "text/plain"
    
    def test_get_recommended_headers_positive(self):
        """Test getting recommended headers for positive test case."""
        endpoint = APIEndpoint(
            method="GET",
            path="/api/v1/users",
            operation_id="getUsers",
            summary="Get users",
            parameters=[]
        )
        
        headers = self.analyzer.get_recommended_headers(endpoint, "positive")
        assert headers == {"Accept": "application/json"}
    
    def test_has_auth_with_security_schemes(self):
        """Test authentication detection with security schemes."""
        spec_data = {
            "components": {
                "securitySchemes": {
                    "bearerAuth": {
                        "type": "http",
                        "scheme": "bearer"
                    }
                }
            }
        }
        
        assert self.analyzer._has_auth(spec_data) is True
    
    def test_has_auth_with_global_security(self):
        """Test authentication detection with global security."""
        spec_data = {
            "security": [{"bearerAuth": []}]
        }
        
        assert self.analyzer._has_auth(spec_data) == True
    
    def test_has_auth_no_auth(self):
        """Test authentication detection without authentication."""
        spec_data = {}
        
        assert self.analyzer._has_auth(spec_data) is False


@pytest.fixture
def sample_endpoint():
    """Sample API endpoint for testing."""
    return APIEndpoint(
        method="GET",
        path="/api/v1/products",
        operation_id="getProducts",
        summary="Get products",
        parameters=[
            APIParameter(
                name="limit",
                location="query",
                type="integer",
                required=False
            )
        ]
    )


@pytest.fixture
def sample_spec_with_auth():
    """Sample API spec with authentication."""
    return {
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT"
                }
            }
        },
        "security": [{"bearerAuth": []}]
    }


class TestHeadersIntegration:
    """Integration tests for headers functionality."""
    
    def test_complete_headers_analysis_flow(self, sample_endpoint, sample_spec_with_auth):
        """Test complete headers analysis workflow."""
        analyzer = HeadersAnalyzer()
        
        scenarios = analyzer.analyze_headers(sample_endpoint, sample_spec_with_auth)
        
        # Verify positive scenario
        assert "positive" in scenarios
        positive_headers = scenarios["positive"]
        assert "Accept" in positive_headers
        assert "Authorization" in positive_headers
        assert positive_headers["Authorization"].startswith("Bearer")
        
        # Verify negative scenarios
        assert "negative_auth_missing" in scenarios
        assert "negative_auth_invalid" in scenarios
        
        # Verify auth missing scenario doesn't have auth header
        auth_missing = scenarios["negative_auth_missing"]
        assert "Authorization" not in auth_missing
        assert "Accept" in auth_missing
        
        # Verify invalid auth scenario has invalid token
        auth_invalid = scenarios["negative_auth_invalid"]
        assert auth_invalid["Authorization"] == "Bearer invalid-token"