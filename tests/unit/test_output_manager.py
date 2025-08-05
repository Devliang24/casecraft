"""Tests for output manager module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from casecraft.core.management.output_manager import OutputManager, OutputError
from casecraft.models.config import OutputConfig
from casecraft.models.test_case import TestCase, TestCaseCollection, TestType, TestCaseMetadata
from datetime import datetime


class TestOutputManager:
    """Test output manager functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.output_config = OutputConfig(directory=self.temp_dir)
        self.manager = OutputManager(self.output_config)
        
        # Create sample test case
        self.test_case = TestCase(
            name="Test successful login",
            description="Test login with valid credentials",
            method="POST",
            path="/api/v1/auth/login",
            headers={"Content-Type": "application/json"},
            body={"username": "test", "password": "pass"},
            expected_status=200,
            test_type=TestType.POSITIVE,
            tags=["auth", "login"],
            metadata=TestCaseMetadata(
                generated_at=datetime.now(),
                api_version="1.0.0",
                llm_model="test-model"
            )
        )
        
        self.collection = TestCaseCollection(
            endpoint_id="POST:/api/v1/auth/login",
            method="POST",
            path="/api/v1/auth/login",
            summary="User login",
            description="Authenticate user",
            tags=["auth"],
            test_cases=[self.test_case]
        )
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_init(self):
        """Test output manager initialization."""
        assert self.manager.output_dir == self.output_dir
        assert self.output_dir.exists()
    
    def test_init_creates_directory(self):
        """Test that init creates output directory if it doesn't exist."""
        new_dir = self.output_dir / "new_output"
        manager = OutputManager(new_dir)
        assert new_dir.exists()
    
    def test_get_output_path_default(self):
        """Test getting output path without organization."""
        endpoint_id = "POST:/api/v1/auth/login"
        path = self.manager.get_output_path(endpoint_id)
        
        assert path.parent == self.output_dir
        assert path.name == "post_api_v1_auth_login_test_cases.json"
    
    def test_get_output_path_with_tag_organization(self):
        """Test getting output path with tag organization."""
        endpoint_id = "POST:/api/v1/auth/login"
        tags = ["auth", "user"]
        
        path = self.manager.get_output_path(endpoint_id, tags, organize_by="tag")
        
        assert path.parent == self.output_dir / "auth"
        assert path.name == "post_api_v1_auth_login_test_cases.json"
    
    def test_get_output_path_no_tags(self):
        """Test getting output path with tag organization but no tags."""
        endpoint_id = "GET:/health"
        
        path = self.manager.get_output_path(endpoint_id, [], organize_by="tag")
        
        assert path.parent == self.output_dir / "uncategorized"
        assert path.name == "get_health_test_cases.json"
    
    def test_sanitize_filename(self):
        """Test filename sanitization."""
        endpoint_id = "GET:/api/v1/users/{id}/profile?full=true"
        filename = self.manager._sanitize_filename(endpoint_id)
        
        assert filename == "get_api_v1_users_id_profile_full_true"
        assert "{" not in filename
        assert "}" not in filename
        assert "?" not in filename
        assert "=" not in filename
    
    def test_save_test_cases(self):
        """Test saving test cases to file."""
        output_path = self.manager.save_test_cases(self.collection)
        
        assert output_path.exists()
        
        # Verify content
        with open(output_path) as f:
            data = json.load(f)
        
        assert data["endpoint_id"] == self.collection.endpoint_id
        assert data["method"] == self.collection.method
        assert data["path"] == self.collection.path
        assert len(data["test_cases"]) == 1
        assert data["test_cases"][0]["name"] == self.test_case.name
    
    def test_save_test_cases_with_organization(self):
        """Test saving test cases with tag organization."""
        output_path = self.manager.save_test_cases(self.collection, organize_by="tag")
        
        assert output_path.exists()
        assert output_path.parent.name == "auth"  # First tag
    
    def test_save_test_cases_creates_subdirectory(self):
        """Test that save creates subdirectories as needed."""
        collection_with_tags = TestCaseCollection(
            endpoint_id="POST:/api/v1/orders",
            method="POST",
            path="/api/v1/orders",
            summary="Create order",
            tags=["orders", "commerce"],
            test_cases=[self.test_case]
        )
        
        output_path = self.manager.save_test_cases(collection_with_tags, organize_by="tag")
        
        assert output_path.exists()
        assert (self.output_dir / "orders").is_dir()
    
    def test_save_test_cases_error_handling(self):
        """Test error handling when saving fails."""
        # Make directory read-only to cause error
        import os
        os.chmod(self.temp_dir, 0o444)
        
        with pytest.raises(OutputError) as exc_info:
            self.manager.save_test_cases(self.collection)
        
        assert "Failed to save test cases" in str(exc_info.value)
        
        # Restore permissions for cleanup
        os.chmod(self.temp_dir, 0o755)
    
    def test_get_saved_files(self):
        """Test getting list of saved files."""
        # Save multiple collections
        self.manager.save_test_cases(self.collection)
        
        collection2 = TestCaseCollection(
            endpoint_id="GET:/api/v1/users",
            method="GET",
            path="/api/v1/users",
            summary="List users",
            tags=["users"],
            test_cases=[self.test_case]
        )
        self.manager.save_test_cases(collection2)
        
        files = self.manager.get_saved_files()
        
        assert len(files) == 2
        assert all(f.suffix == ".json" for f in files)
        assert any("auth_login" in f.name for f in files)
        assert any("users" in f.name for f in files)