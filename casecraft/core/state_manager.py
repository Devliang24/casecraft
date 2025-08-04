"""State management for incremental test case generation."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import aiofiles
from pydantic import ValidationError

from casecraft.models.api_spec import APIEndpoint, APISpecification
from casecraft.models.state import CaseCraftState, EndpointState, ProjectConfig, ProcessingStatistics


class StateError(Exception):
    """State management related errors."""
    pass


class StateManager:
    """Manages state for incremental test case generation."""
    
    def __init__(self, state_file_path: Optional[Path] = None):
        """Initialize state manager.
        
        Args:
            state_file_path: Optional custom path to state file.
                           Defaults to .casecraft_state.json in current directory
        """
        self.state_file_path = state_file_path or Path(".casecraft_state.json")
        self._state: Optional[CaseCraftState] = None
    
    async def load_state(self) -> CaseCraftState:
        """Load state from file.
        
        Returns:
            Loaded state or new state if file doesn't exist
            
        Raises:
            StateError: If state file is corrupted
        """
        if self._state is not None:
            return self._state
        
        if not self.state_file_path.exists():
            self._state = CaseCraftState()
            return self._state
        
        try:
            async with aiofiles.open(self.state_file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            if not content.strip():
                self._state = CaseCraftState()
                return self._state
            
            state_data = json.loads(content)
            self._state = CaseCraftState(**state_data)
            return self._state
            
        except json.JSONDecodeError as e:
            raise StateError(f"Invalid JSON in state file: {e}") from e
        except ValidationError as e:
            raise StateError(f"Invalid state file format: {e}") from e
        except OSError as e:
            raise StateError(f"Failed to read state file: {e}") from e
    
    async def save_state(self, state: Optional[CaseCraftState] = None) -> None:
        """Save state to file.
        
        Args:
            state: State to save, uses current state if None
            
        Raises:
            StateError: If unable to save state
        """
        if state is None:
            state = self._state
        
        if state is None:
            raise StateError("No state to save")
        
        try:
            # Convert to JSON with proper datetime serialization
            state_json = state.model_dump_json(indent=2)
            
            async with aiofiles.open(self.state_file_path, 'w', encoding='utf-8') as f:
                await f.write(state_json)
            
            self._state = state
            
        except OSError as e:
            raise StateError(f"Failed to save state file: {e}") from e
    
    async def update_project_config(
        self,
        api_source: str,
        api_content: str
    ) -> None:
        """Update project configuration in state.
        
        Args:
            api_source: API source URL or file path
            api_content: Raw API content for hashing
        """
        state = await self.load_state()
        
        source_hash = self._compute_content_hash(api_content)
        
        state.config = ProjectConfig(
            api_source=api_source,
            last_modified=datetime.now(),
            source_hash=source_hash
        )
        
        await self.save_state(state)
    
    async def analyze_changes(
        self,
        api_spec: APISpecification,
        api_content: str
    ) -> Dict[str, Set[str]]:
        """Analyze what endpoints have changed since last run.
        
        Args:
            api_spec: Current API specification
            api_content: Raw API content
            
        Returns:
            Dictionary with sets of endpoint IDs:
            - new: Newly added endpoints
            - changed: Endpoints with definition changes
            - unchanged: Endpoints that haven't changed
            - removed: Endpoints that were removed
        """
        state = await self.load_state()
        
        current_endpoints = {ep.get_endpoint_id(): ep for ep in api_spec.endpoints}
        stored_endpoints = set(state.endpoints.keys())
        current_endpoint_ids = set(current_endpoints.keys())
        
        new_endpoints = current_endpoint_ids - stored_endpoints
        removed_endpoints = stored_endpoints - current_endpoint_ids
        potentially_changed = current_endpoint_ids & stored_endpoints
        
        changed_endpoints = set()
        unchanged_endpoints = set()
        
        for endpoint_id in potentially_changed:
            endpoint = current_endpoints[endpoint_id]
            endpoint_hash = self._compute_endpoint_hash(endpoint)
            
            stored_state = state.get_endpoint_state(endpoint_id)
            if stored_state is None or stored_state.definition_hash != endpoint_hash:
                changed_endpoints.add(endpoint_id)
            else:
                unchanged_endpoints.add(endpoint_id)
        
        return {
            "new": new_endpoints,
            "changed": changed_endpoints,
            "unchanged": unchanged_endpoints,
            "removed": removed_endpoints
        }
    
    async def should_generate_endpoint(
        self,
        endpoint: APIEndpoint,
        force: bool = False
    ) -> bool:
        """Check if endpoint should be generated.
        
        Args:
            endpoint: API endpoint to check
            force: Force generation regardless of state
            
        Returns:
            True if endpoint should be generated
        """
        if force:
            return True
        
        state = await self.load_state()
        endpoint_id = endpoint.get_endpoint_id()
        endpoint_hash = self._compute_endpoint_hash(endpoint)
        
        stored_state = state.get_endpoint_state(endpoint_id)
        
        # Generate if endpoint is new or changed
        return stored_state is None or stored_state.definition_hash != endpoint_hash
    
    async def mark_endpoint_generated(
        self,
        endpoint: APIEndpoint,
        test_cases_count: int,
        output_file: Optional[str] = None
    ) -> None:
        """Mark endpoint as generated with current state.
        
        Args:
            endpoint: Generated endpoint
            test_cases_count: Number of test cases generated
            output_file: Path to output file
        """
        state = await self.load_state()
        endpoint_id = endpoint.get_endpoint_id()
        endpoint_hash = self._compute_endpoint_hash(endpoint)
        
        endpoint_state = EndpointState(
            definition_hash=endpoint_hash,
            last_generated=datetime.now(),
            test_cases_count=test_cases_count,
            output_file=output_file
        )
        
        state.update_endpoint_state(endpoint_id, endpoint_state)
        await self.save_state(state)
    
    async def update_statistics(
        self,
        total_endpoints: int,
        generated_count: int,
        skipped_count: int,
        failed_count: int = 0,
        duration: Optional[float] = None
    ) -> None:
        """Update processing statistics.
        
        Args:
            total_endpoints: Total number of endpoints processed
            generated_count: Number of endpoints generated
            skipped_count: Number of endpoints skipped
            failed_count: Number of endpoints that failed
            duration: Processing duration in seconds
        """
        state = await self.load_state()
        
        state.statistics = ProcessingStatistics(
            total_endpoints=total_endpoints,
            generated_count=generated_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            last_run_duration=duration
        )
        
        await self.save_state(state)
    
    async def get_generation_summary(self) -> Dict[str, any]:
        """Get summary of last generation run.
        
        Returns:
            Summary dictionary with statistics and metadata
        """
        state = await self.load_state()
        
        return {
            "version": state.version,
            "last_run": state.statistics.last_run_duration,
            "total_endpoints": state.statistics.total_endpoints,
            "generated": state.statistics.generated_count,
            "skipped": state.statistics.skipped_count,
            "failed": state.statistics.failed_count,
            "endpoints": len(state.endpoints),
            "api_source": state.config.api_source if state.config else None,
            "last_modified": state.config.last_modified if state.config else None
        }
    
    async def cleanup_removed_endpoints(self, current_endpoint_ids: Set[str]) -> None:
        """Remove state for endpoints that no longer exist.
        
        Args:
            current_endpoint_ids: Set of current endpoint IDs
        """
        state = await self.load_state()
        
        # Find endpoints to remove
        stored_endpoint_ids = set(state.endpoints.keys())
        removed_endpoints = stored_endpoint_ids - current_endpoint_ids
        
        if not removed_endpoints:
            return
        
        # Remove from state
        for endpoint_id in removed_endpoints:
            del state.endpoints[endpoint_id]
        
        await self.save_state(state)
    
    def _compute_content_hash(self, content: str) -> str:
        """Compute MD5 hash of content.
        
        Args:
            content: Content to hash
            
        Returns:
            MD5 hash string
        """
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _compute_endpoint_hash(self, endpoint: APIEndpoint) -> str:
        """Compute hash of endpoint definition for change detection.
        
        Args:
            endpoint: API endpoint
            
        Returns:
            MD5 hash string
        """
        # Create a normalized representation for hashing
        endpoint_dict = {
            "method": endpoint.method,
            "path": endpoint.path,
            "operation_id": endpoint.operation_id,
            "summary": endpoint.summary,
            "description": endpoint.description,
            "tags": sorted(endpoint.tags) if endpoint.tags else [],
            "parameters": [
                {
                    "name": p.name,
                    "location": p.location,
                    "type": p.type,
                    "required": p.required,
                    "description": p.description,
                    "schema": p.param_schema
                }
                for p in sorted(endpoint.parameters, key=lambda x: (x.location, x.name))
            ] if endpoint.parameters else [],
            "request_body": endpoint.request_body,
            "responses": endpoint.responses
        }
        
        # Convert to JSON for consistent hashing
        endpoint_json = json.dumps(endpoint_dict, sort_keys=True, separators=(',', ':'))
        return hashlib.md5(endpoint_json.encode('utf-8')).hexdigest()
    
    async def get_endpoints_to_process(
        self,
        api_spec: APISpecification,
        force: bool = False
    ) -> Dict[str, List[APIEndpoint]]:
        """Get endpoints categorized by processing need.
        
        Args:
            api_spec: API specification
            force: Force processing all endpoints
            
        Returns:
            Dictionary with endpoint lists:
            - to_generate: Endpoints that need generation
            - to_skip: Endpoints that can be skipped
        """
        to_generate = []
        to_skip = []
        
        for endpoint in api_spec.endpoints:
            if await self.should_generate_endpoint(endpoint, force):
                to_generate.append(endpoint)
            else:
                to_skip.append(endpoint)
        
        return {
            "to_generate": to_generate,
            "to_skip": to_skip
        }
    
    def state_file_exists(self) -> bool:
        """Check if state file exists."""
        return self.state_file_path.exists()
    
    async def reset_state(self) -> None:
        """Reset state to empty."""
        self._state = CaseCraftState()
        await self.save_state()