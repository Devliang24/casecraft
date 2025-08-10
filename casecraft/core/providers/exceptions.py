"""Exceptions for provider system."""


class ProviderError(Exception):
    """Base exception for provider-related errors."""
    pass


class ProviderNotFoundError(ProviderError):
    """Raised when a provider is not found."""
    pass


class ProviderConfigError(ProviderError):
    """Raised when provider configuration is invalid."""
    pass


class ProviderHealthCheckError(ProviderError):
    """Raised when provider health check fails."""
    pass


class ProviderGenerationError(ProviderError):
    """Raised when provider fails to generate content."""
    pass


class ProviderRateLimitError(ProviderError):
    """Raised when provider rate limit is exceeded."""
    pass