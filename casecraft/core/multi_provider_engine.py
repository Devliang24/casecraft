"""Multi-provider execution engine for test case generation."""

import asyncio
from typing import Dict, List, Optional, Any
import logging
from pathlib import Path

from casecraft.core.providers.registry import ProviderRegistry
from casecraft.core.providers.base import LLMProvider
from casecraft.core.providers.exceptions import ProviderError, ProviderGenerationError
from casecraft.models.api_spec import APIEndpoint
from casecraft.models.provider_config import MultiProviderConfig
from casecraft.core.providers.strategies.base import ProviderStrategy
from casecraft.core.providers.strategies.round_robin import RoundRobinStrategy
from casecraft.core.providers.strategies.random_strategy import RandomStrategy
from casecraft.core.providers.strategies.complexity_strategy import ComplexityBasedStrategy
from casecraft.core.providers.fallback import FallbackHandler
from casecraft.core.management.output_manager import OutputManager
from casecraft.models.test_case import TestCaseCollection


class GenerationResult:
    """Result from multi-provider generation."""
    
    def __init__(self):
        self.successful_endpoints: List[str] = []
        self.failed_endpoints: List[str] = []
        self.provider_usage: Dict[str, int] = {}
        self.total_tokens: int = 0
        self.errors: List[str] = []
        self.generated_files: List[Path] = []


class MultiProviderEngine:
    """Multi-provider concurrent execution engine."""
    
    def __init__(self, config: MultiProviderConfig, output_dir: str = "test_cases", state_manager=None):
        """Initialize multi-provider engine.
        
        Args:
            config: Multi-provider configuration
            output_dir: Output directory for test cases
            state_manager: Optional state manager for tracking generation state
        """
        self.config = config
        self.registry = ProviderRegistry()
        self.logger = logging.getLogger("engine.multi_provider")
        self.fallback_handler = FallbackHandler(config) if config.fallback_enabled else None
        self.state_manager = state_manager
        
        # Initialize output manager
        from casecraft.models.config import OutputConfig
        output_config = OutputConfig(directory=output_dir)
        self.output_manager = OutputManager(output_config)
        
        # Initialize strategy
        self.strategy = self._create_strategy()
        
        # Initialize providers
        self._initialize_providers()
    
    def _create_strategy(self) -> ProviderStrategy:
        """Create provider assignment strategy.
        
        Returns:
            Provider strategy instance
        """
        strategy_name = self.config.strategy.lower()
        active_providers = self.config.get_active_providers()
        
        if strategy_name == "round_robin":
            return RoundRobinStrategy(active_providers)
        elif strategy_name == "random":
            return RandomStrategy(active_providers)
        elif strategy_name == "complexity_based":
            return ComplexityBasedStrategy(active_providers)
        elif strategy_name == "manual":
            # Manual strategy doesn't need a strategy object
            return None
        else:
            # Default to round robin
            self.logger.warning(f"Unknown strategy {strategy_name}, using round_robin")
            return RoundRobinStrategy(active_providers)
    
    def _initialize_providers(self) -> None:
        """Initialize all configured providers."""
        for provider_name in self.config.get_active_providers():
            if provider_name not in self.config.configs:
                self.logger.warning(f"Provider {provider_name} listed but not configured")
                continue
            
            provider_config = self.config.configs[provider_name]
            
            try:
                # Convert to base provider config
                from casecraft.core.management.multi_provider_config_manager import MultiProviderConfigManager
                manager = MultiProviderConfigManager(load_env=False)
                base_config = manager.convert_to_base_config(provider_config)
                
                # Register and get provider
                # First register the provider class if not already registered
                if provider_name.lower() == "glm":
                    from casecraft.core.providers.glm_provider import GLMProvider
                    self.registry.register("glm", GLMProvider)
                # Add more provider registrations here
                
                # Get provider instance
                provider = self.registry.get_provider(provider_name, base_config)
                self.logger.info(f"Initialized provider: {provider_name}")
                
            except Exception as e:
                self.logger.error(f"Failed to initialize provider {provider_name}: {e}")
    
    async def generate_with_providers(
        self,
        endpoints: List[APIEndpoint],
        provider_assignments: Optional[Dict[str, str]] = None
    ) -> GenerationResult:
        """Generate test cases using multiple providers concurrently.
        
        Args:
            endpoints: List of API endpoints
            provider_assignments: Optional manual provider assignments
            
        Returns:
            Generation result
        """
        result = GenerationResult()
        
        # Assign providers to endpoints
        if provider_assignments:
            # Use manual assignments, but need to map paths to endpoint IDs
            mapped_assignments = {}
            for endpoint in endpoints:
                endpoint_id = endpoint.get_endpoint_id()
                # Check if path matches any mapping
                for path_pattern, provider in provider_assignments.items():
                    if path_pattern in endpoint.path:
                        mapped_assignments[endpoint_id] = provider
                        break
                # If no mapping found, use strategy
                if endpoint_id not in mapped_assignments:
                    provider = self.strategy.get_next_provider(endpoint)
                    mapped_assignments[endpoint_id] = provider
            provider_assignments = mapped_assignments
        else:
            provider_assignments = self._assign_providers(endpoints)
        
        # Group endpoints by provider
        provider_groups = self._group_by_provider(endpoints, provider_assignments)
        
        # Create concurrent tasks for each provider
        tasks = []
        for provider_name, provider_endpoints in provider_groups.items():
            try:
                provider = self.registry.get_provider(provider_name)
                max_workers = provider.get_max_workers()
                
                # Create batch generation task
                task = self._generate_batch(
                    provider,
                    provider_endpoints,
                    max_workers,
                    result
                )
                tasks.append(task)
                
            except Exception as e:
                self.logger.error(f"Failed to create task for provider {provider_name}: {e}")
                result.errors.append(f"Provider {provider_name}: {e}")
        
        # Execute all tasks concurrently
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        return result
    
    def _assign_providers(self, endpoints: List[APIEndpoint]) -> Dict[str, str]:
        """Assign providers to endpoints using the configured strategy.
        
        Args:
            endpoints: List of API endpoints
            
        Returns:
            Dictionary mapping endpoint IDs to provider names
        """
        assignments = {}
        
        for endpoint in endpoints:
            provider = self.strategy.get_next_provider(endpoint)
            assignments[endpoint.get_endpoint_id()] = provider
            
        return assignments
    
    def _group_by_provider(
        self,
        endpoints: List[APIEndpoint],
        assignments: Dict[str, str]
    ) -> Dict[str, List[APIEndpoint]]:
        """Group endpoints by assigned provider.
        
        Args:
            endpoints: List of API endpoints
            assignments: Provider assignments
            
        Returns:
            Dictionary mapping provider names to endpoint lists
        """
        groups = {}
        
        for endpoint in endpoints:
            endpoint_id = endpoint.get_endpoint_id()
            provider = assignments.get(endpoint_id)
            
            if provider:
                if provider not in groups:
                    groups[provider] = []
                groups[provider].append(endpoint)
        
        return groups
    
    async def _generate_batch(
        self,
        provider: LLMProvider,
        endpoints: List[APIEndpoint],
        max_workers: int,
        result: GenerationResult
    ) -> None:
        """Generate test cases for a batch of endpoints using a single provider.
        
        Args:
            provider: LLM provider
            endpoints: List of endpoints
            max_workers: Maximum concurrent workers
            result: Result object to update
        """
        semaphore = asyncio.Semaphore(max_workers)
        
        async def generate_with_semaphore(endpoint: APIEndpoint):
            async with semaphore:
                endpoint_id = endpoint.get_endpoint_id()
                
                try:
                    if self.config.fallback_enabled and self.fallback_handler:
                        # Use fallback handler
                        test_cases, token_usage = await self.fallback_handler.generate_with_fallback(
                            endpoint,
                            provider,
                            self.config.fallback_chain
                        )
                    else:
                        # Direct generation
                        test_cases, token_usage = await provider.generate_test_cases(endpoint)
                    
                    # Save test cases to file
                    output_file = await self.output_manager.save_test_cases(test_cases)
                    result.generated_files.append(output_file)
                    
                    # Update result
                    result.successful_endpoints.append(endpoint_id)
                    
                    # Update provider usage
                    provider_name = provider.name
                    if provider_name not in result.provider_usage:
                        result.provider_usage[provider_name] = 0
                    result.provider_usage[provider_name] += 1
                    
                    # Update token usage
                    if token_usage:
                        result.total_tokens += token_usage.total_tokens
                    
                    # Update state manager if available
                    if self.state_manager:
                        test_cases_count = len(test_cases.test_cases) if hasattr(test_cases, 'test_cases') else 5
                        await self.state_manager.mark_endpoint_generated(
                            endpoint=endpoint,
                            test_cases_count=test_cases_count,
                            output_file=str(output_file),
                            provider_used=provider_name,
                            tokens_used=token_usage.total_tokens if token_usage else 0
                        )
                        
                        self.state_manager.complete_provider_request(
                            provider=provider_name,
                            endpoint_id=endpoint_id,
                            success=True,
                            tokens=token_usage.total_tokens if token_usage else 0
                        )
                    
                    self.logger.info(f"Generated test cases for {endpoint_id} using {provider.name}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to generate for {endpoint_id}: {e}")
                    result.failed_endpoints.append(endpoint_id)
                    result.errors.append(f"{endpoint_id}: {e}")
                    
                    # Update state manager for failure if available
                    if self.state_manager:
                        self.state_manager.complete_provider_request(
                            provider=provider.name,
                            endpoint_id=endpoint_id,
                            success=False,
                            error_type=str(type(e).__name__)
                        )
        
        # Create tasks for all endpoints
        tasks = [generate_with_semaphore(endpoint) for endpoint in endpoints]
        
        # Execute all tasks
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def health_check_all(self) -> Dict[str, bool]:
        """Perform health check on all providers.
        
        Returns:
            Dictionary mapping provider names to health status
        """
        health_status = {}
        
        for provider_name in self.registry.list_instances():
            try:
                provider = self.registry.get_provider(provider_name)
                is_healthy = await provider.health_check()
                health_status[provider_name] = is_healthy
                
                if is_healthy:
                    self.logger.info(f"Provider {provider_name} is healthy")
                else:
                    self.logger.warning(f"Provider {provider_name} health check failed")
                    
            except Exception as e:
                self.logger.error(f"Health check error for {provider_name}: {e}")
                health_status[provider_name] = False
        
        return health_status
    
    async def close(self) -> None:
        """Clean up all resources."""
        await self.registry.close_all()
        self.logger.info("Multi-provider engine closed")