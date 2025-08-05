"""Tests for state manager."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from casecraft.core.management.state_manager import StateManager, StateError
from casecraft.models.api_spec import APIEndpoint, APISpecification, APIParameter
from casecraft.models.state import CaseCraftState, EndpointState, ProjectConfig


class TestStateManager:
    """Test state manager functionality."""
    
    def test_init_default_path(self):
        """Test initialization with default path."""
        manager = StateManager()
        assert manager.state_file_path == Path(".casecraft_state.json")
    
    def test_init_custom_path(self, tmp_path):
        """Test initialization with custom path."""
        custom_path = tmp_path / "custom_state.json"
        manager = StateManager(custom_path)
        assert manager.state_file_path == custom_path
    
    @pytest.mark.asyncio
    async def test_load_state_new_file(self, tmp_path):
        """Test loading state when file doesn't exist."""
        state_path = tmp_path / "new_state.json"
        manager = StateManager(state_path)
        
        state = await manager.load_state()
        
        assert isinstance(state, CaseCraftState)
        assert state.version == "1.0"
        assert len(state.endpoints) == 0
        assert state.config is None
    
    @pytest.mark.asyncio
    async def test_load_state_empty_file(self, tmp_path):
        """Test loading state from empty file."""
        state_path = tmp_path / "empty_state.json"
        state_path.write_text("")  # Empty file
        
        manager = StateManager(state_path)
        state = await manager.load_state()
        
        assert isinstance(state, CaseCraftState)
        assert state.version == "1.0"
    
    @pytest.mark.asyncio
    async def test_load_state_existing_file(self, tmp_path):
        """Test loading state from existing file."""
        state_path = tmp_path / "existing_state.json"
        
        # Create test state data
        test_state = {
            "version": "1.0",
            "config": {
                "api_source": "test.yaml",
                "last_modified": "2024-01-01T12:00:00",
                "source_hash": "abc123"
            },
            "endpoints": {
                "GET:/users": {
                    "definition_hash": "def456",
                    "last_generated": "2024-01-01T12:00:00",
                    "test_cases_count": 5,
                    "output_file": "get_users.json"
                }
            },
            "statistics": {
                "total_endpoints": 1,
                "generated_count": 1,
                "skipped_count": 0,
                "failed_count": 0
            }
        }
        
        state_path.write_text(json.dumps(test_state))
        
        manager = StateManager(state_path)
        state = await manager.load_state()
        
        assert state.version == "1.0"
        assert state.config.api_source == "test.yaml"
        assert len(state.endpoints) == 1
        assert "GET:/users" in state.endpoints
    
    @pytest.mark.asyncio
    async def test_load_state_invalid_json(self, tmp_path):
        """Test loading state with invalid JSON."""
        state_path = tmp_path / "invalid_state.json"
        state_path.write_text("{ invalid json }")
        
        manager = StateManager(state_path)
        
        with pytest.raises(StateError, match="Invalid JSON"):
            await manager.load_state()
    
    @pytest.mark.asyncio
    async def test_save_and_load_cycle(self, tmp_path):
        """Test save and load state cycle."""
        state_path = tmp_path / "cycle_state.json"
        manager = StateManager(state_path)
        
        # Load initial state
        state = await manager.load_state()
        
        # Modify state
        state.config = ProjectConfig(
            api_source="test.yaml",
            last_modified=datetime.now(),
            source_hash="test123"
        )
        
        # Save state
        await manager.save_state(state)
        
        # Create new manager and load
        new_manager = StateManager(state_path)
        loaded_state = await new_manager.load_state()
        
        assert loaded_state.config.api_source == "test.yaml"
        assert loaded_state.config.source_hash == "test123"
    
    @pytest.mark.asyncio
    async def test_update_project_config(self, tmp_path):
        """Test updating project configuration."""
        state_path = tmp_path / "config_state.json"
        manager = StateManager(state_path)
        
        await manager.update_project_config("https://api.example.com/openapi.json", "test content")
        
        state = await manager.load_state()
        assert state.config.api_source == "https://api.example.com/openapi.json"
        assert state.config.source_hash is not None
        assert len(state.config.source_hash) == 32  # MD5 hash length
    
    @pytest.mark.asyncio
    async def test_analyze_changes_new_spec(self, tmp_path):
        """Test analyzing changes with new API spec."""
        state_path = tmp_path / "changes_state.json"
        manager = StateManager(state_path)
        
        # Create API spec
        endpoints = [
            APIEndpoint(method="GET", path="/users"),
            APIEndpoint(method="POST", path="/users")
        ]
        api_spec = APISpecification(title="Test API", version="1.0", endpoints=endpoints)
        
        changes = await manager.analyze_changes(api_spec, "content")
        
        assert len(changes["new"]) == 2
        assert "GET:/users" in changes["new"]
        assert "POST:/users" in changes["new"]
        assert len(changes["changed"]) == 0
        assert len(changes["unchanged"]) == 0
        assert len(changes["removed"]) == 0
    
    @pytest.mark.asyncio
    async def test_analyze_changes_with_existing_state(self, tmp_path):
        """Test analyzing changes with existing state."""
        state_path = tmp_path / "existing_changes_state.json"
        manager = StateManager(state_path)
        
        # Set up existing state
        endpoint1 = APIEndpoint(method="GET", path="/users")
        endpoint2 = APIEndpoint(method="POST", path="/users")
        
        await manager.mark_endpoint_generated(endpoint1, 5)
        await manager.mark_endpoint_generated(endpoint2, 3)
        
        # Create modified API spec (change endpoint1, keep endpoint2, add endpoint3)
        endpoint1_modified = APIEndpoint(method="GET", path="/users", summary="Modified summary")
        endpoint2_unchanged = APIEndpoint(method="POST", path="/users")
        endpoint3_new = APIEndpoint(method="DELETE", path="/users/{id}")
        
        api_spec = APISpecification(
            title="Test API",
            version="1.0", 
            endpoints=[endpoint1_modified, endpoint2_unchanged, endpoint3_new]
        )
        
        changes = await manager.analyze_changes(api_spec, "content")
        
        assert "DELETE:/users/{id}" in changes["new"]
        assert "GET:/users" in changes["changed"]  # Modified summary
        assert "POST:/users" in changes["unchanged"]
        assert len(changes["removed"]) == 0
    
    @pytest.mark.asyncio
    async def test_should_generate_endpoint_force(self, tmp_path):
        """Test should_generate_endpoint with force flag."""
        state_path = tmp_path / "force_state.json"
        manager = StateManager(state_path)
        
        endpoint = APIEndpoint(method="GET", path="/users")
        
        # Should generate when forced
        assert await manager.should_generate_endpoint(endpoint, force=True)
        
        # Mark as generated
        await manager.mark_endpoint_generated(endpoint, 5)
        
        # Should still generate when forced
        assert await manager.should_generate_endpoint(endpoint, force=True)
        
        # Should not generate without force
        assert not await manager.should_generate_endpoint(endpoint, force=False)
    
    @pytest.mark.asyncio
    async def test_mark_endpoint_generated(self, tmp_path):
        """Test marking endpoint as generated."""
        state_path = tmp_path / "generated_state.json"
        manager = StateManager(state_path)
        
        endpoint = APIEndpoint(method="GET", path="/users", summary="List users")
        
        await manager.mark_endpoint_generated(endpoint, 7, "output/get_users.json")
        
        state = await manager.load_state()
        endpoint_state = state.get_endpoint_state("GET:/users")
        
        assert endpoint_state is not None
        assert endpoint_state.test_cases_count == 7
        assert endpoint_state.output_file == "output/get_users.json"
        assert endpoint_state.definition_hash is not None
    
    @pytest.mark.asyncio
    async def test_update_statistics(self, tmp_path):
        """Test updating processing statistics."""
        state_path = tmp_path / "stats_state.json"
        manager = StateManager(state_path)
        
        await manager.update_statistics(
            total_endpoints=10,
            generated_count=7,
            skipped_count=2,
            failed_count=1,
            duration=45.5
        )
        
        state = await manager.load_state()
        stats = state.statistics
        
        assert stats.total_endpoints == 10
        assert stats.generated_count == 7
        assert stats.skipped_count == 2
        assert stats.failed_count == 1
        assert stats.last_run_duration == 45.5
    
    @pytest.mark.asyncio
    async def test_get_generation_summary(self, tmp_path):
        """Test getting generation summary."""
        state_path = tmp_path / "summary_state.json"
        manager = StateManager(state_path)
        
        # Set up state
        await manager.update_project_config("test.yaml", "content")
        await manager.update_statistics(5, 3, 2, 0, 30.0)
        
        summary = await manager.get_generation_summary()
        
        assert summary["version"] == "1.0"
        assert summary["total_endpoints"] == 5
        assert summary["generated"] == 3
        assert summary["skipped"] == 2
        assert summary["failed"] == 0
        assert summary["last_run"] == 30.0
        assert summary["api_source"] == "test.yaml"
    
    @pytest.mark.asyncio
    async def test_cleanup_removed_endpoints(self, tmp_path):
        """Test cleaning up removed endpoints."""
        state_path = tmp_path / "cleanup_state.json"
        manager = StateManager(state_path)
        
        # Add some endpoints to state
        endpoint1 = APIEndpoint(method="GET", path="/users")
        endpoint2 = APIEndpoint(method="POST", path="/users")
        endpoint3 = APIEndpoint(method="DELETE", path="/users/{id}")
        
        await manager.mark_endpoint_generated(endpoint1, 5)
        await manager.mark_endpoint_generated(endpoint2, 3)
        await manager.mark_endpoint_generated(endpoint3, 2)
        
        # Current endpoints (endpoint3 removed)
        current_ids = {"GET:/users", "POST:/users"}
        
        await manager.cleanup_removed_endpoints(current_ids)
        
        state = await manager.load_state()
        assert len(state.endpoints) == 2
        assert "GET:/users" in state.endpoints
        assert "POST:/users" in state.endpoints
        assert "DELETE:/users/{id}" not in state.endpoints
    
    @pytest.mark.asyncio
    async def test_get_endpoints_to_process(self, tmp_path):
        """Test getting endpoints to process."""
        state_path = tmp_path / "process_state.json"
        manager = StateManager(state_path)
        
        # Create endpoints
        endpoint1 = APIEndpoint(method="GET", path="/users")
        endpoint2 = APIEndpoint(method="POST", path="/users")
        endpoint3 = APIEndpoint(method="DELETE", path="/users/{id}")
        
        api_spec = APISpecification(
            title="Test API",
            version="1.0",
            endpoints=[endpoint1, endpoint2, endpoint3]
        )
        
        # Mark one endpoint as already generated
        await manager.mark_endpoint_generated(endpoint1, 5)
        
        result = await manager.get_endpoints_to_process(api_spec, force=False)
        
        assert len(result["to_generate"]) == 2  # endpoint2 and endpoint3
        assert len(result["to_skip"]) == 1     # endpoint1
        
        # Test with force=True
        result_force = await manager.get_endpoints_to_process(api_spec, force=True)
        
        assert len(result_force["to_generate"]) == 3  # All endpoints
        assert len(result_force["to_skip"]) == 0
    
    def test_state_file_exists(self, tmp_path):
        """Test state file existence check."""
        state_path = tmp_path / "exists_state.json"
        manager = StateManager(state_path)
        
        assert not manager.state_file_exists()
        
        state_path.touch()
        assert manager.state_file_exists()
    
    @pytest.mark.asyncio
    async def test_reset_state(self, tmp_path):
        """Test resetting state."""
        state_path = tmp_path / "reset_state.json"
        manager = StateManager(state_path)
        
        # Set up some state
        await manager.update_project_config("test.yaml", "content")
        endpoint = APIEndpoint(method="GET", path="/users")
        await manager.mark_endpoint_generated(endpoint, 5)
        
        # Reset state
        await manager.reset_state()
        
        state = await manager.load_state()
        assert state.config is None
        assert len(state.endpoints) == 0
    
    def test_compute_content_hash(self, tmp_path):
        """Test content hash computation."""
        manager = StateManager()
        
        hash1 = manager._compute_content_hash("test content")
        hash2 = manager._compute_content_hash("test content")
        hash3 = manager._compute_content_hash("different content")
        
        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 32  # MD5 hash length
    
    def test_compute_endpoint_hash(self, tmp_path):
        """Test endpoint hash computation."""
        manager = StateManager()
        
        endpoint1 = APIEndpoint(
            method="GET",
            path="/users",
            summary="List users",
            parameters=[
                APIParameter(name="limit", location="query", type="integer")
            ]
        )
        
        endpoint2 = APIEndpoint(
            method="GET",
            path="/users",
            summary="List users",
            parameters=[
                APIParameter(name="limit", location="query", type="integer")
            ]
        )
        
        endpoint3 = APIEndpoint(
            method="GET",
            path="/users",
            summary="Different summary",  # Changed summary
            parameters=[
                APIParameter(name="limit", location="query", type="integer")
            ]
        )
        
        hash1 = manager._compute_endpoint_hash(endpoint1)
        hash2 = manager._compute_endpoint_hash(endpoint2)
        hash3 = manager._compute_endpoint_hash(endpoint3)
        
        assert hash1 == hash2  # Same endpoints
        assert hash1 != hash3  # Different summary