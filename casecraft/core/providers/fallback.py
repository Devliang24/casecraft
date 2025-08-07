"""Fallback handler for provider failures."""

import asyncio
from typing import List, Optional, Tuple
import logging

from casecraft.core.providers.base import LLMProvider
from casecraft.core.providers.registry import ProviderRegistry
from casecraft.core.providers.exceptions import (
    ProviderGenerationError,
    ProviderRateLimitError
)
from casecraft.models.api_spec import APIEndpoint
from casecraft.models.test_case import TestCaseCollection
from casecraft.models.usage import TokenUsage
from casecraft.models.provider_config import MultiProviderConfig


class FallbackHandler:
    """Handles provider fallback and retry logic."""
    
    def __init__(self, config: MultiProviderConfig):
        """Initialize fallback handler.
        
        Args:
            config: Multi-provider configuration
        """
        self.config = config
        self.registry = ProviderRegistry()
        self.logger = logging.getLogger("provider.fallback")
    
    async def generate_with_fallback(
        self,
        endpoint: APIEndpoint,
        primary_provider: LLMProvider,
        fallback_chain: List[str]
    ) -> Tuple[TestCaseCollection, Optional[TokenUsage]]:
        """Generate test cases with fallback mechanism.
        
        Args:
            endpoint: API endpoint
            primary_provider: Primary provider to use
            fallback_chain: List of fallback provider names
            
        Returns:
            Tuple of (test cases, token usage)
            
        Raises:
            ProviderGenerationError: If all providers fail
        """
        providers_tried = []
        last_error = None
        
        # Build complete provider chain
        provider_chain = [primary_provider.name] + [
            p for p in fallback_chain if p != primary_provider.name
        ]
        
        for provider_name in provider_chain:
            providers_tried.append(provider_name)
            
            try:
                # Get provider instance
                if provider_name == primary_provider.name:
                    provider = primary_provider
                else:
                    # Check if provider is configured
                    if provider_name not in self.config.configs:
                        self.logger.warning(f"Provider {provider_name} not configured, skipping")
                        continue
                    
                    # Get provider from registry
                    provider = self.registry.get_provider(provider_name)
                
                # Try to generate test cases
                self.logger.info(f"Trying provider {provider_name} for {endpoint.get_endpoint_id()}")
                
                test_cases, token_usage = await provider.generate_test_cases(endpoint)
                
                # If we used a fallback provider, log it
                if provider_name != primary_provider.name:
                    self.logger.info(
                        f"Successfully used fallback provider {provider_name} "
                        f"for {endpoint.get_endpoint_id()}"
                    )
                    
                    # Add fallback metadata to test cases if possible
                    if hasattr(test_cases, 'metadata'):
                        if test_cases.metadata is None:
                            test_cases.metadata = {}
                        test_cases.metadata['fallback_from'] = primary_provider.name
                        test_cases.metadata['providers_tried'] = providers_tried
                
                return test_cases, token_usage
                
            except ProviderRateLimitError as e:
                last_error = e
                self.logger.warning(
                    f"Provider {provider_name} rate limited for {endpoint.get_endpoint_id()}: {e}"
                )
                
                # Wait before trying next provider
                await asyncio.sleep(5)
                continue
                
            except Exception as e:
                last_error = e
                self.logger.warning(
                    f"Provider {provider_name} failed for {endpoint.get_endpoint_id()}: {e}"
                )
                continue
        
        # All providers failed
        error_msg = (
            f"All providers failed for {endpoint.get_endpoint_id()}. "
            f"Tried: {providers_tried}. Last error: {last_error}"
        )
        self.logger.error(error_msg)
        raise ProviderGenerationError(error_msg)