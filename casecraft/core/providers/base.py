"""Base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Callable
import logging

from casecraft.models.api_spec import APIEndpoint
from casecraft.models.test_case import TestCaseCollection
from casecraft.models.usage import TokenUsage


class LLMResponse:
    """Response from LLM provider."""
    
    def __init__(
        self, 
        content: str,
        provider: str,
        model: str,
        token_usage: Optional[TokenUsage] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Initialize LLM response.
        
        Args:
            content: Response content
            provider: Provider name
            model: Model name
            token_usage: Token usage information
            metadata: Additional metadata
        """
        self.content = content
        self.provider = provider
        self.model = model
        self.token_usage = token_usage
        self.metadata = metadata or {}


class ProviderConfig:
    """Configuration for a provider."""
    
    def __init__(
        self,
        name: str,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 60,
        max_retries: int = 3,
        temperature: float = 0.7,
        stream: bool = False,
        workers: int = 1,
        **kwargs
    ):
        """Initialize provider configuration.
        
        Args:
            name: Provider name
            model: Model name
            api_key: API key
            base_url: Base URL for API
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries
            temperature: Temperature for generation
            stream: Whether to stream responses
            workers: Maximum concurrent workers
            **kwargs: Additional provider-specific options
        """
        self.name = name
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.temperature = temperature
        self.stream = stream
        self.workers = workers
        self.extra = kwargs


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    def __init__(self, config: ProviderConfig):
        """Initialize LLM provider.
        
        Args:
            config: Provider configuration
        """
        self.config = config
        self.logger = logging.getLogger(f"provider.{self.name}")
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Get provider name.
        
        Returns:
            Provider name
        """
        pass
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate response from prompt.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt
            progress_callback: Callback for progress updates
            **kwargs: Additional generation parameters
            
        Returns:
            LLM response
        """
        pass
    
    @abstractmethod
    async def generate_test_cases(
        self,
        endpoint: APIEndpoint,
        progress_callback: Optional[Callable[[float], None]] = None,
        **kwargs
    ) -> tuple[TestCaseCollection, Optional[TokenUsage]]:
        """Generate test cases for an API endpoint.
        
        Args:
            endpoint: API endpoint
            progress_callback: Callback for progress updates
            **kwargs: Additional generation parameters
            
        Returns:
            Tuple of (test cases, token usage)
        """
        pass
    
    @abstractmethod
    def get_max_workers(self) -> int:
        """Get maximum concurrent workers for this provider.
        
        Returns:
            Maximum number of concurrent workers
        """
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """Validate provider configuration.
        
        Returns:
            True if configuration is valid
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check provider health.
        
        Returns:
            True if provider is healthy
        """
        pass
    
    async def close(self) -> None:
        """Clean up provider resources."""
        pass