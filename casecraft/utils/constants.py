"""Global constants for CaseCraft.

This module defines all hardcoded constants used throughout the application.
By centralizing constants here, we improve maintainability and make it easier
to configure values through environment variables.
"""

from http import HTTPStatus


# ====================
# HTTP Status Codes
# ====================

# Rate limiting status code
HTTP_RATE_LIMIT = 429

# Server error status codes that should trigger retries
HTTP_SERVER_ERRORS = [500, 502, 503]


# ====================
# Timeout Settings (seconds)
# ====================

# General request timeouts
DEFAULT_REQUEST_TIMEOUT = 120
DEFAULT_PROVIDER_TIMEOUT = 60

# API parsing timeout - used when downloading and parsing OpenAPI specs
DEFAULT_API_PARSE_TIMEOUT = 30


# ====================
# Retry and Delay Settings
# ====================

# Maximum retry attempts
DEFAULT_MAX_RETRIES = 5
DEFAULT_PROVIDER_MAX_RETRIES = 3

# Delay settings (in seconds)
DEFAULT_ERROR_RETRY_DELAY = 2.0       # Delay after errors before next operation
DEFAULT_RETRY_BACKOFF_DELAY = 5.0     # Exponential backoff delay between retries
DEFAULT_PROVIDER_SWITCH_DELAY = 5.0   # Delay when switching to fallback provider


# ====================
# Port Settings
# ====================

# Local provider default ports
DEFAULT_OLLAMA_PORT = 11434
DEFAULT_VLLM_PORT = 8000
DEFAULT_LOCAL_PORT = 8000


# ====================
# Model Settings
# ====================

# Token limits and model parameters
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 0.7

