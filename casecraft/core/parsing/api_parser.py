"""API documentation parser for OpenAPI/Swagger specifications."""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import httpx
import yaml
from jsonschema import validate, ValidationError as JsonSchemaValidationError

from casecraft.models.api_spec import APIEndpoint, APIParameter, APISpecification


class APIParseError(Exception):
    """API parsing related errors."""
    pass


class APIParser:
    """Parses OpenAPI/Swagger API documentation."""
    
    def __init__(self, timeout: int = 30):
        """Initialize API parser.
        
        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout
        self._openapi_v3_schema = None
        self._swagger_v2_schema = None
    
    async def parse_from_source(self, source: str) -> APISpecification:
        """Parse API specification from URL or file path.
        
        Args:
            source: URL or file path to API documentation
            
        Returns:
            Parsed API specification
            
        Raises:
            APIParseError: If unable to parse the API documentation
        """
        if self._is_url(source):
            content = await self._fetch_from_url(source)
        else:
            content = await self._read_from_file(source)
        
        return self._parse_content(content, source)
    
    def parse_from_content(self, content: str, source_name: str = "content") -> APISpecification:
        """Parse API specification from string content.
        
        Args:
            content: API documentation content
            source_name: Name/identifier for the content source
            
        Returns:
            Parsed API specification
        """
        return self._parse_content(content, source_name)
    
    def get_content_hash(self, content: str) -> str:
        """Generate MD5 hash of content for change detection.
        
        Args:
            content: Content to hash
            
        Returns:
            MD5 hash string
        """
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _is_url(self, source: str) -> bool:
        """Check if source is a URL."""
        try:
            result = urlparse(source)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    async def _fetch_from_url(self, url: str) -> str:
        """Fetch API documentation from URL.
        
        Args:
            url: URL to fetch from
            
        Returns:
            Content as string
            
        Raises:
            APIParseError: If unable to fetch content
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
        except httpx.HTTPError as e:
            raise APIParseError(f"Failed to fetch API documentation from {url}: {e}") from e
        except Exception as e:
            raise APIParseError(f"Unexpected error fetching from {url}: {e}") from e
    
    async def _read_from_file(self, file_path: str) -> str:
        """Read API documentation from file.
        
        Args:
            file_path: Path to file
            
        Returns:
            File content as string
            
        Raises:
            APIParseError: If unable to read file
        """
        try:
            path = Path(file_path)
            if not path.exists():
                raise APIParseError(f"File not found: {file_path}")
            
            return path.read_text(encoding='utf-8')
        except UnicodeDecodeError as e:
            raise APIParseError(f"Failed to decode file {file_path}: {e}") from e
        except OSError as e:
            raise APIParseError(f"Failed to read file {file_path}: {e}") from e
    
    def _parse_content(self, content: str, source_name: str) -> APISpecification:
        """Parse API documentation content.
        
        Args:
            content: Raw content string
            source_name: Name/identifier for the content
            
        Returns:
            Parsed API specification
        """
        # Parse as JSON or YAML
        try:
            if content.strip().startswith('{'):
                data = json.loads(content)
            else:
                data = yaml.safe_load(content)
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            raise APIParseError(f"Invalid JSON/YAML in {source_name}: {e}") from e
        
        if not isinstance(data, dict):
            raise APIParseError(f"API documentation must be a JSON/YAML object in {source_name}")
        
        # Determine format and parse
        if 'openapi' in data:
            return self._parse_openapi_v3(data, source_name)
        elif 'swagger' in data:
            return self._parse_swagger_v2(data, source_name)
        else:
            raise APIParseError(
                f"Unsupported API documentation format in {source_name}. "
                "Expected OpenAPI 3.x or Swagger 2.x"
            )
    
    def _parse_openapi_v3(self, data: Dict[str, Any], source_name: str) -> APISpecification:
        """Parse OpenAPI 3.x specification.
        
        Args:
            data: Parsed OpenAPI data
            source_name: Source identifier
            
        Returns:
            API specification
        """
        try:
            # Extract basic info
            info = data.get('info', {})
            title = info.get('title', 'Unknown API')
            version = info.get('version', '1.0.0')
            description = info.get('description')
            
            # Extract base URL from servers
            base_url = None
            servers = data.get('servers', [])
            if servers and isinstance(servers[0], dict):
                base_url = servers[0].get('url')
            
            # Parse endpoints
            endpoints = []
            paths = data.get('paths', {})
            
            for path, path_obj in paths.items():
                if not isinstance(path_obj, dict):
                    continue
                    
                for method, operation in path_obj.items():
                    if method.startswith('x-') or method in ['parameters', 'summary', 'description']:
                        continue
                    
                    if not isinstance(operation, dict):
                        continue
                    
                    endpoint = self._parse_openapi_operation(
                        method.upper(), path, operation, data
                    )
                    if endpoint:
                        endpoints.append(endpoint)
            
            return APISpecification(
                title=title,
                version=version,
                description=description,
                base_url=base_url,
                endpoints=endpoints
            )
            
        except Exception as e:
            raise APIParseError(f"Failed to parse OpenAPI specification from {source_name}: {e}") from e
    
    def _parse_openapi_operation(
        self, 
        method: str, 
        path: str, 
        operation: Dict[str, Any],
        spec_data: Dict[str, Any]
    ) -> Optional[APIEndpoint]:
        """Parse single OpenAPI operation.
        
        Args:
            method: HTTP method
            path: API path
            operation: Operation object
            spec_data: Full specification data for resolving references
            
        Returns:
            Parsed endpoint or None if invalid
        """
        try:
            # Basic info
            operation_id = operation.get('operationId')
            summary = operation.get('summary')
            description = operation.get('description')
            tags = operation.get('tags', [])
            
            # Parse parameters
            parameters = []
            for param in operation.get('parameters', []):
                if '$ref' in param:
                    param = self._resolve_reference(param['$ref'], spec_data)
                
                api_param = APIParameter(
                    name=param.get('name', ''),
                    location=param.get('in', ''),
                    type=self._extract_parameter_type(param),
                    required=param.get('required', False),
                    description=param.get('description'),
                    param_schema=param.get('schema')
                )
                parameters.append(api_param)
            
            # Parse request body
            request_body = None
            if 'requestBody' in operation:
                rb = operation['requestBody']
                if '$ref' in rb:
                    rb = self._resolve_reference(rb['$ref'], spec_data)
                request_body = rb
            
            # Parse responses
            responses = {}
            for status_code, response in operation.get('responses', {}).items():
                if '$ref' in response:
                    response = self._resolve_reference(response['$ref'], spec_data)
                responses[status_code] = response
            
            return APIEndpoint(
                method=method,
                path=path,
                operation_id=operation_id,
                summary=summary,
                description=description,
                tags=tags,
                parameters=parameters,
                request_body=request_body,
                responses=responses
            )
            
        except Exception:
            # Skip invalid operations rather than failing entire parse
            return None
    
    def _parse_swagger_v2(self, data: Dict[str, Any], source_name: str) -> APISpecification:
        """Parse Swagger 2.x specification.
        
        Args:
            data: Parsed Swagger data
            source_name: Source identifier
            
        Returns:
            API specification
        """
        try:
            # Extract basic info
            info = data.get('info', {})
            title = info.get('title', 'Unknown API')
            version = info.get('version', '1.0.0')
            description = info.get('description')
            
            # Extract base URL
            base_url = None
            host = data.get('host')
            base_path = data.get('basePath', '')
            schemes = data.get('schemes', ['https'])
            if host:
                scheme = schemes[0] if schemes else 'https'
                base_url = f"{scheme}://{host}{base_path}"
            
            # Parse endpoints
            endpoints = []
            paths = data.get('paths', {})
            
            for path, path_obj in paths.items():
                if not isinstance(path_obj, dict):
                    continue
                    
                for method, operation in path_obj.items():
                    if method.startswith('x-') or method in ['parameters']:
                        continue
                    
                    if not isinstance(operation, dict):
                        continue
                    
                    endpoint = self._parse_swagger_operation(
                        method.upper(), path, operation, data
                    )
                    if endpoint:
                        endpoints.append(endpoint)
            
            return APISpecification(
                title=title,
                version=version,
                description=description,
                base_url=base_url,
                endpoints=endpoints
            )
            
        except Exception as e:
            raise APIParseError(f"Failed to parse Swagger specification from {source_name}: {e}") from e
    
    def _parse_swagger_operation(
        self,
        method: str,
        path: str,
        operation: Dict[str, Any],
        spec_data: Dict[str, Any]
    ) -> Optional[APIEndpoint]:
        """Parse single Swagger operation.
        
        Args:
            method: HTTP method
            path: API path
            operation: Operation object
            spec_data: Full specification data
            
        Returns:
            Parsed endpoint or None if invalid
        """
        try:
            # Basic info
            operation_id = operation.get('operationId')
            summary = operation.get('summary')
            description = operation.get('description')
            tags = operation.get('tags', [])
            
            # Parse parameters
            parameters = []
            for param in operation.get('parameters', []):
                if '$ref' in param:
                    param = self._resolve_reference(param['$ref'], spec_data)
                
                param_type = param.get('type', 'string')
                if param.get('in') == 'body' and 'schema' in param:
                    param_type = 'object'
                
                api_param = APIParameter(
                    name=param.get('name', ''),
                    location=param.get('in', ''),
                    type=param_type,
                    required=param.get('required', False),
                    description=param.get('description'),
                    param_schema=param.get('schema')
                )
                parameters.append(api_param)
            
            # For Swagger, request body is in parameters with in: body
            request_body = None
            body_params = [p for p in operation.get('parameters', []) if p.get('in') == 'body']
            if body_params:
                body_param = body_params[0]
                if '$ref' in body_param:
                    body_param = self._resolve_reference(body_param['$ref'], spec_data)
                request_body = {
                    'description': body_param.get('description'),
                    'required': body_param.get('required', False),
                    'schema': body_param.get('schema')
                }
            
            # Parse responses
            responses = operation.get('responses', {})
            
            return APIEndpoint(
                method=method,
                path=path,
                operation_id=operation_id,
                summary=summary,
                description=description,
                tags=tags,
                parameters=parameters,
                request_body=request_body,
                responses=responses
            )
            
        except Exception:
            # Skip invalid operations
            return None
    
    def _extract_parameter_type(self, param: Dict[str, Any]) -> str:
        """Extract parameter type from OpenAPI parameter definition."""
        if 'schema' in param:
            return param['schema'].get('type', 'string')
        return param.get('type', 'string')
    
    def _resolve_reference(self, ref: str, spec_data: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve JSON reference.
        
        Args:
            ref: Reference string like "#/components/schemas/User"
            spec_data: Full specification data
            
        Returns:
            Resolved object
        """
        if not ref.startswith('#/'):
            return {}
        
        path = ref[2:].split('/')
        current = spec_data
        
        try:
            for part in path:
                current = current[part]
            return current
        except (KeyError, TypeError):
            return {}
    
    def _path_matches(self, endpoint_path: str, pattern: str) -> bool:
        """Smart path matching that handles trailing slash differences.
        
        Args:
            endpoint_path: The endpoint path from API spec
            pattern: The pattern to match against
            
        Returns:
            True if paths match (considering trailing slash flexibility)
        """
        import fnmatch
        
        # Normalize paths by removing trailing slashes for comparison
        def normalize_path(path: str) -> str:
            return path.rstrip('/')
        
        endpoint_normalized = normalize_path(endpoint_path)
        pattern_normalized = normalize_path(pattern)
        
        # Try exact match first (normalized)
        if endpoint_normalized == pattern_normalized:
            return True
        
        # Try fnmatch with both original and normalized versions
        if fnmatch.fnmatch(endpoint_path, pattern):
            return True
        
        if fnmatch.fnmatch(endpoint_normalized, pattern_normalized):
            return True
        
        # Try substring matching (for backward compatibility)
        if pattern in endpoint_path or pattern_normalized in endpoint_normalized:
            return True
        
        return False
    
    def filter_endpoints(
        self,
        spec: APISpecification,
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
        include_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None
    ) -> APISpecification:
        """Filter endpoints based on criteria.
        
        Args:
            spec: API specification to filter
            include_tags: Tags to include (if any match)
            exclude_tags: Tags to exclude (if any match)
            include_paths: Path patterns to include
            exclude_paths: Path patterns to exclude
            
        Returns:
            Filtered API specification
        """
        import fnmatch
        
        filtered_endpoints = []
        
        for endpoint in spec.endpoints:
            # Check tag filters
            if include_tags:
                if not any(tag in endpoint.tags for tag in include_tags):
                    continue
            
            if exclude_tags:
                if any(tag in endpoint.tags for tag in exclude_tags):
                    continue
            
            # Check path filters
            if include_paths:
                if not any(self._path_matches(endpoint.path, pattern) for pattern in include_paths):
                    continue
            
            if exclude_paths:
                if any(self._path_matches(endpoint.path, pattern) for pattern in exclude_paths):
                    continue
            
            filtered_endpoints.append(endpoint)
        
        return APISpecification(
            title=spec.title,
            version=spec.version,
            description=spec.description,
            base_url=spec.base_url,
            endpoints=filtered_endpoints
        )