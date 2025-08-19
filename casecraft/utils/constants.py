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


# ====================
# Provider Configuration
# ====================

# Provider Base URLs
PROVIDER_BASE_URLS = {
    'glm': 'https://open.bigmodel.cn/api/paas/v4',
    'qwen': 'https://dashscope.aliyuncs.com/api/v1',
    'deepseek': 'https://api.deepseek.com/v1',
    'kimi': 'https://api.moonshot.cn/v1',
}

# Provider Concurrency Limits
PROVIDER_MAX_WORKERS = {
    'glm': 1,       # GLM only supports single concurrency
    'qwen': 3,      # Qwen default workers
    'deepseek': 3,  # DeepSeek default workers
    'kimi': 2,      # Kimi default workers
    'local': 4,     # Local model workers
}

# Provider Retry Configuration
PROVIDER_RETRY_MAX_WAIT = 30.0  # Maximum wait time for retries


# ====================
# Progress Bar Configuration
# ====================

PROGRESS_MAX_NO_STREAM = 0.90      # Max progress for non-streaming mode
PROGRESS_MAX_WITH_STREAM = 0.92    # Max progress for streaming mode
PROGRESS_COMPLETION_BONUS = 0.02   # Bonus progress on completion
PROGRESS_RETRY_PENALTY = 0.10      # Progress penalty for retries
PROGRESS_MIN_AFTER_PENALTY = 0.10  # Minimum progress after penalty


# ====================
# File System Configuration
# ====================

STATE_FILE_NAME = '.casecraft_state.json'
CONFIG_FILE_NAME = 'config.yaml'
CONFIG_DIR_NAME = '.casecraft'
DEFAULT_OUTPUT_DIR = 'test_cases'
DEFAULT_LOG_DIR = 'logs'
ENV_FILE_NAME = '.env'

# File Operation Settings
DEFAULT_BATCH_SIZE = 10
DEFAULT_CONCURRENCY_LIMIT = 4


# ====================
# UI Display Configuration
# ====================

# Color scheme for Rich output
UI_COLORS = {
    'success': 'green',
    'error': 'red',
    'warning': 'yellow',
    'info': 'cyan',
    'dim': 'dim',
    'bold': 'bold',
    'highlight': 'magenta',
}

# Icons for different states
UI_ICONS = {
    'success': '✓',
    'error': '✗',
    'warning': '⚠️',
    'info': 'ℹ️',
    'loading': '⏳',
    'sparkles': '✨',
    'folder': '📁',
    'file': '📄',
}


# ====================
# Model Configuration
# ====================

# Valid models for each provider
PROVIDER_MODELS = {
    'glm': ['glm-4.5-x', 'glm-4.5-air', 'glm-4.5-airx', 'glm-4', 'glm-3-turbo'],
    'qwen': ['qwen-max', 'qwen-plus', 'qwen-turbo', 'qwen-long'],
    'deepseek': ['deepseek-chat', 'deepseek-coder', 'deepseek-v2', 'deepseek-v2.5'],
    'kimi': ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'],
}


# ====================
# Cleanup Configuration
# ====================

DEFAULT_KEEP_DAYS = 7  # Default days to keep logs
MIN_KEEP_DAYS = 1
MAX_KEEP_DAYS = 365

