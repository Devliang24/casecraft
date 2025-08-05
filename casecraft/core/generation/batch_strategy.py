"""BigModel optimized batch execution strategy for API test generation."""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging

from casecraft.models.api_spec import APIEndpoint
from casecraft.models.config import LLMConfig


class APIComplexity(Enum):
    """API endpoint complexity levels."""
    SIMPLE = "simple"       # No params or body, GET only
    MEDIUM = "medium"       # Few params, simple body
    COMPLEX = "complex"     # Many params, complex body, auth required


@dataclass
class BatchExecutionPlan:
    """Execution plan for batch processing."""
    
    batches: List[List[APIEndpoint]]
    estimated_time: float
    
    def total_endpoints(self) -> int:
        """Get total number of endpoints."""
        return sum(len(batch) for batch in self.batches)
    
    def batch_summary(self) -> List[Dict[str, any]]:
        """Get summary of each batch."""
        summaries = []
        for i, batch in enumerate(self.batches):
            summaries.append({
                "batch_number": i + 1,
                "endpoints": len(batch),
                "complexity": self._analyze_batch_complexity(batch)
            })
        return summaries
    
    def _analyze_batch_complexity(self, batch: List[APIEndpoint]) -> str:
        """Analyze overall complexity of a batch."""
        complexities = [classify_endpoint_complexity(ep) for ep in batch]
        if all(c == APIComplexity.SIMPLE for c in complexities):
            return "simple"
        elif any(c == APIComplexity.COMPLEX for c in complexities):
            return "complex"
        else:
            return "medium"


class BatchStrategyManager:
    """Manages batch execution strategies optimized for BigModel."""
    
    def __init__(self, llm_config: LLMConfig):
        """Initialize batch strategy manager.
        
        Args:
            llm_config: LLM configuration
        """
        self.llm_config = llm_config
        self.logger = logging.getLogger(__name__)
    
    def create_execution_plan(
        self,
        endpoints: List[APIEndpoint],
        batch_size: int = 8
    ) -> BatchExecutionPlan:
        """Create an execution plan for endpoints optimized for BigModel.
        
        Args:
            endpoints: List of API endpoints to process
            batch_size: Size of each batch for progress tracking
            
        Returns:
            Batch execution plan
        """
        if not endpoints:
            return BatchExecutionPlan([], 0.0)
        
        # Sort by complexity - simple first for quick wins
        sorted_endpoints = self._sort_by_complexity(endpoints)
        
        # Create batches for progress tracking
        batches = []
        for i in range(0, len(sorted_endpoints), batch_size):
            batches.append(sorted_endpoints[i:i + batch_size])
        
        # Estimate time: ~5 seconds per endpoint with BigModel
        estimated_time = len(endpoints) * 5.0
        
        return BatchExecutionPlan(
            batches=batches,
            estimated_time=estimated_time
        )
    
    def _sort_by_complexity(self, endpoints: List[APIEndpoint]) -> List[APIEndpoint]:
        """Sort endpoints by complexity (simple first).
        
        Args:
            endpoints: List of endpoints
            
        Returns:
            Sorted endpoints
        """
        def complexity_score(ep: APIEndpoint) -> int:
            complexity = classify_endpoint_complexity(ep)
            if complexity == APIComplexity.SIMPLE:
                return 0
            elif complexity == APIComplexity.MEDIUM:
                return 1
            else:
                return 2
        
        return sorted(endpoints, key=complexity_score)


def classify_endpoint_complexity(endpoint: APIEndpoint) -> APIComplexity:
    """Classify an endpoint's complexity.
    
    Args:
        endpoint: API endpoint
        
    Returns:
        Complexity level
    """
    param_count = len(endpoint.parameters) if endpoint.parameters else 0
    has_body = endpoint.request_body is not None
    has_auth = any(
        param.name.lower() in ["authorization", "x-api-key", "api-key"]
        for param in (endpoint.parameters or [])
        if param.location == "header"
    )
    
    # Simple: GET with no params, no auth
    if endpoint.method.upper() == "GET" and param_count <= 2 and not has_auth:
        return APIComplexity.SIMPLE
    
    # Complex: Many params, auth required, or complex body
    if param_count > 5 or has_auth or (has_body and endpoint.method.upper() in ["POST", "PUT"]):
        return APIComplexity.COMPLEX
    
    # Everything else is medium
    return APIComplexity.MEDIUM


class AdaptiveBatchProcessor:
    """Adaptive batch processor with error recovery for BigModel."""
    
    def __init__(self):
        """Initialize adaptive processor."""
        self.failed_endpoints: List[Tuple[APIEndpoint, str]] = []
        self.logger = logging.getLogger(__name__)
    
    async def process_with_recovery(
        self,
        execution_plan: BatchExecutionPlan,
        process_func,
        progress_callback=None
    ) -> Dict[str, any]:
        """Process batches with automatic error recovery.
        
        Args:
            execution_plan: Batch execution plan
            process_func: Async function to process each endpoint
            progress_callback: Optional callback for progress updates
            
        Returns:
            Processing results
        """
        results = {
            "successful": [],
            "failed": [],
            "recovered": [],
            "total_time": 0.0
        }
        
        start_time = asyncio.get_event_loop().time()
        
        # Process each batch sequentially (BigModel single concurrency)
        for i, batch in enumerate(execution_plan.batches):
            batch_results = await self._process_batch_sequential(
                batch, process_func, f"Batch {i+1}/{len(execution_plan.batches)}"
            )
            
            results["successful"].extend(batch_results["successful"])
            self.failed_endpoints.extend(batch_results["failed"])
            
            if progress_callback:
                progress_callback(i + 1, len(execution_plan.batches))
        
        # Retry failed endpoints with longer delays
        if self.failed_endpoints:
            recovery_results = await self._recover_failed_endpoints(process_func)
            results["recovered"] = recovery_results["recovered"]
            results["failed"] = recovery_results["failed"]
        
        results["total_time"] = asyncio.get_event_loop().time() - start_time
        return results
    
    async def _process_batch_sequential(
        self,
        batch: List[APIEndpoint],
        process_func,
        batch_name: str
    ) -> Dict[str, List]:
        """Process a batch of endpoints sequentially.
        
        Args:
            batch: List of endpoints
            process_func: Processing function
            batch_name: Batch identifier
            
        Returns:
            Batch results
        """
        results = {"successful": [], "failed": []}
        
        for endpoint in batch:
            try:
                result = await process_func(endpoint)
                results["successful"].append((endpoint, result))
            except Exception as e:
                self.logger.error(f"Failed to process {endpoint.get_endpoint_id()}: {e}")
                results["failed"].append((endpoint, str(e)))
                
                # Add small delay after errors to avoid rate limits
                await asyncio.sleep(2.0)
        
        return results
    
    async def _recover_failed_endpoints(self, process_func) -> Dict[str, List]:
        """Attempt to recover failed endpoints.
        
        Args:
            process_func: Processing function
            
        Returns:
            Recovery results
        """
        if not self.failed_endpoints:
            return {"recovered": [], "failed": []}
        
        self.logger.info(f"Attempting to recover {len(self.failed_endpoints)} failed endpoints")
        
        results = {"recovered": [], "failed": []}
        
        # Process failed endpoints with longer delays
        for endpoint, original_error in self.failed_endpoints:
            try:
                # Add longer delay between retries
                await asyncio.sleep(5.0)
                
                result = await process_func(endpoint, retry=True)
                results["recovered"].append((endpoint, result))
                self.logger.info(f"Successfully recovered {endpoint.get_endpoint_id()}")
            except Exception as e:
                results["failed"].append((endpoint, f"{original_error} -> Retry: {str(e)}"))
                self.logger.error(f"Failed to recover {endpoint.get_endpoint_id()}: {e}")
        
        return results