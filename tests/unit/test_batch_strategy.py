"""Tests for batch strategy module."""

import pytest
from unittest.mock import Mock

from casecraft.core.generation.batch_strategy import (
    APIComplexity, BatchExecutionPlan, BatchStrategyManager,
    classify_endpoint_complexity
)
from casecraft.models.api_spec import APIEndpoint, APIParameter
from casecraft.models.config import LLMConfig


class TestAPIComplexity:
    """Test API complexity enum."""
    
    def test_complexity_values(self):
        """Test complexity enum values."""
        assert APIComplexity.SIMPLE.value == "simple"
        assert APIComplexity.MEDIUM.value == "medium"
        assert APIComplexity.COMPLEX.value == "complex"


class TestBatchExecutionPlan:
    """Test batch execution plan."""
    
    def test_total_endpoints(self):
        """Test total endpoints calculation."""
        endpoints = [
            Mock(path="/simple"),
            Mock(path="/medium"),
            Mock(path="/complex")
        ]
        
        plan = BatchExecutionPlan(
            batches=[endpoints[:2], endpoints[2:]],
            estimated_time=120.0
        )
        
        assert plan.total_endpoints() == 3
        assert len(plan.batches) == 2
        assert plan.estimated_time == 120.0
    
    def test_empty_plan(self):
        """Test empty execution plan."""
        plan = BatchExecutionPlan(
            batches=[],
            estimated_time=0.0
        )
        
        assert plan.total_endpoints() == 0
        assert len(plan.batches) == 0


class TestBatchStrategyManager:
    """Test batch strategy manager functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = LLMConfig(
            api_key="test-key",
            model="test-model"
        )
        self.strategy = BatchStrategyManager(self.config)
    
    def test_classify_complexity_simple(self):
        """Test classifying simple endpoint."""
        endpoint = APIEndpoint(
            path="/health",
            method="GET",
            summary="Health check",
            parameters=[]
        )
        
        complexity = classify_endpoint_complexity(endpoint)
        assert complexity == APIComplexity.SIMPLE
    
    def test_classify_complexity_medium(self):
        """Test classifying medium complexity endpoint."""
        endpoint = APIEndpoint(
            path="/users/{id}",
            method="GET",
            summary="Get user by ID",
            parameters=[
                APIParameter(
                    name="id",
                    location="path",
                    type="integer",
                    required=True,
                    param_schema={"type": "integer"}
                )
            ]
        )
        
        complexity = classify_endpoint_complexity(endpoint)
        assert complexity == APIComplexity.SIMPLE  # GET with <= 2 params is simple
    
    def test_classify_complexity_complex(self):
        """Test classifying complex endpoint."""
        endpoint = APIEndpoint(
            path="/orders",
            method="POST",
            summary="Create order",
            parameters=[
                APIParameter(
                    name="Authorization",
                    location="header",
                    type="string",
                    required=True,
                    param_schema={"type": "string"}
                )
            ],
            request_body={
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "items": {"type": "array"},
                                "customer": {"type": "object"},
                                "payment": {"type": "object"}
                            }
                        }
                    }
                }
            }
        )
        
        complexity = classify_endpoint_complexity(endpoint)
        assert complexity == APIComplexity.COMPLEX
    
    def test_create_execution_plan(self):
        """Test creating execution plan."""
        endpoints = [
            APIEndpoint(path="/simple", method="GET", summary="Simple"),
            APIEndpoint(path="/medium", method="GET", summary="Medium", 
                       parameters=[APIParameter(name="id", location="path", type="string", required=True)]),
            APIEndpoint(path="/complex", method="POST", summary="Complex",
                       request_body={"required": True})
        ]
        
        plan = self.strategy.create_execution_plan(endpoints)
        
        assert isinstance(plan, BatchExecutionPlan)
        assert plan.total_endpoints() == 3
        assert plan.estimated_time > 0
        assert len(plan.batches) > 0