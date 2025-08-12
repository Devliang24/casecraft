# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CaseCraft** is a CLI tool for API testing that parses API documentation (OpenAPI/Swagger) and uses BigModel LLM to generate structured test case data in JSON format.

## BigModel API Configuration

For development and testing, you can use the following BigModel API configuration:

```yaml
llm:
  provider: bigmodel
  model: glm-4.5-x
  api_key: db474e8a869844bbbdcf1a111a5eafa4.0SY1uazDVWJQZPHA
  base_url: https://open.bigmodel.cn/api/paas/v4
  timeout: 60
  max_retries: 3
```

**Important Notes:**
- This API key is for development/testing only
- Never commit sensitive API keys to public repositories in production
- The key should be stored in `~/.casecraft/config.yaml` or environment variables
- BigModel GLM-4.5-X model currently generates 8-10 test cases per endpoint

## Core Architecture Requirements

### Command Structure
- `casecraft init` - Initialize configuration with secure API key storage in `~/.casecraft/config.yaml`
- `casecraft generate <source>` - Generate test cases from API docs (URL or local file)
- Support for filtering: `--include-tag`, `--exclude-tag`, `--include-path`
- Concurrent processing: `--workers N` (BigModel only supports 1)
- Force regeneration: `--force`
- Preview mode: `--dry-run`

### Key Components to Implement

1. **Configuration Management**
   - Secure API key storage in user home directory
   - Configuration priority: CLI args > env vars > config file
   - Never log sensitive information

2. **API Documentation Processing** 
   - Support OpenAPI 3.0 and Swagger 2.0 (JSON/YAML)
   - Load from URLs and local file system
   - Interface filtering by tags and path patterns

3. **LLM Integration**
   - BigModel GLM-4.5-X integration with single concurrency
   - Single LLM call per API endpoint to generate all test cases
   - Rate limiting and retry logic for HTTP 429 errors
   - Generate positive (2), negative (3-4), and boundary (1-2) test cases

4. **Incremental Generation**
   - Track API changes in `.casecraft_state.json`
   - Skip unchanged endpoints to avoid unnecessary LLM calls
   - Support force refresh when needed

5. **Output Management**
   - MVP: JSON format only (one file per API endpoint)
   - Optional organization by tag into subdirectories
   - Future: Support for pytest, jest, and Postman collections

### Test Case Coverage Requirements

**Dynamic Test Case Generation Based on Complexity (Updated 2025-08-05)**

The system now evaluates endpoint complexity and adjusts test case requirements accordingly:

1. **Simple Endpoints** (complexity score ≤ 5)
   - Total: 5-6 test cases
   - Positive: 2 cases
   - Negative: 2-3 cases
   - Boundary: 1 case
   - Examples: Simple GET endpoints without parameters

2. **Medium Complexity** (complexity score 6-10)
   - Total: 7-9 test cases
   - Positive: 2-3 cases
   - Negative: 3-4 cases
   - Boundary: 1-2 cases
   - Examples: GET with query parameters, simple POST operations

3. **Complex Endpoints** (complexity score > 10)
   - Total: 10-12 test cases
   - Positive: 3-4 cases
   - Negative: 4-5 cases
   - Boundary: 2-3 cases
   - Examples: POST/PUT with nested request bodies, multiple parameters

**Complexity Factors:**
- Number of parameters (path, query, header)
- Request body complexity (nested objects, arrays)
- Operation type (POST/PUT/PATCH add complexity)
- Authentication requirements
- Number of response types

**Quality over Quantity:**
The system prioritizes generating meaningful test cases over meeting arbitrary numbers. Each test case should have a clear purpose and avoid redundancy.

### Development Guidelines

- Use modular architecture for easy extensibility
- Separate core logic from external dependencies (LLM API, file system) for testability
- Follow Unix philosophy for CLI design
- Provide comprehensive error handling with actionable messages
- Never hardcode API keys or include them in logs/state files

### Technical Constraints

- MVP focuses only on JSON output format
- Concurrent processing should be the primary performance optimization
- Network I/O to LLM should be the main bottleneck, not computation
- Support both Chinese and English in documentation and error messages

## Commands for Development

### Setup and Installation
```bash
# Install for development with all dependencies
make install-dev

# Install for production use
make install
```

### Testing Commands
```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run integration tests only  
make test-integration

# Run tests with coverage report
make test-cov
```

### Code Quality
```bash
# Run linting
make lint

# Format code
make format

# Type checking
make type-check

# Run all quality checks
make quality
```

### Build and Distribution
```bash
# Clean build artifacts
make clean

# Build distribution packages
make build
```

## Architecture Overview

### Core Components

The core module is organized into functional sub-packages:

#### Parsing Module (`casecraft/core/parsing/`)
**API Documentation Processing (`api_parser.py`)**
- Supports OpenAPI 3.0 and Swagger 2.0 (JSON/YAML)
- Loads from URLs and local file system  
- Advanced filtering by tags and path patterns

**Headers Analysis (`headers_analyzer.py`)**
- Analyzes API endpoints for authentication requirements
- Recommends appropriate header scenarios for testing
- Generates environment variable style placeholders for authentication tokens:
  - Bearer Token: `${AUTH_TOKEN}`, `${USER_TOKEN}`, `${ADMIN_TOKEN}`
  - API Key: `${API_KEY}`
  - Basic Auth: `${BASIC_CREDENTIALS}`
  - Invalid tokens: `${INVALID_TOKEN}`, `${INVALID_API_KEY}`

#### Generation Module (`casecraft/core/generation/`)
**LLM Integration (`llm_client.py`)**
- BigModel GLM-4.5-X client implementation with single concurrency
- Built-in rate limiting and retry logic for HTTP 429 errors
- Structured error handling for different failure modes

**Test Case Generation (`test_generator.py`)**
- Single LLM call per API endpoint generates all test cases
- Enforces coverage requirements (2+ positive, 3+ negative, boundary cases)
- JSON schema validation for generated test cases

**Batch Strategy (`batch_strategy.py`)**
- Optimizes batch processing for BigModel API
- Classifies endpoint complexity for efficient processing

#### Management Module (`casecraft/core/management/`)
**Configuration Management (`config_manager.py`)**
- Handles secure API key storage in `~/.casecraft/config.yaml`
- Supports environment variable overrides (`CASECRAFT_*`)
- Configuration priority: CLI args > env vars > config file
- Automatic `.env` file loading from current working directory
- Environment variable mapping:
  - `CASECRAFT_LLM_MODEL` → `llm.model`
  - `CASECRAFT_LLM_API_KEY` → `llm.api_key`
  - `CASECRAFT_LLM_BASE_URL` → `llm.base_url`
  - `CASECRAFT_LLM_TIMEOUT` → `llm.timeout`
  - `CASECRAFT_LLM_MAX_RETRIES` → `llm.max_retries`

**Incremental Generation (`state_manager.py`)**
- Tracks API changes in `.casecraft_state.json`
- Skip unchanged endpoints to avoid unnecessary LLM calls
- Content-based hashing for change detection

**Output Management (`output_manager.py`)**
- JSON format output (one file per API endpoint)
- Optional organization by tag into subdirectories
- File naming templates and conflict resolution

#### Main Engine (`casecraft/core/engine.py`)
- Coordinates all components for test generation
- Manages concurrent processing and error handling
- Provides progress tracking and reporting

### Data Models (`casecraft/models/`)

All data structures use Pydantic for validation:
- `TestCase` - Individual test case with metadata
- `APISpecification` - Parsed API documentation
- `CaseCraftConfig` - Complete configuration structure
- `CaseCraftState` - State tracking for incremental generation

### CLI Interface (`casecraft/cli/`)

**Primary Commands:**
- `casecraft init` - Interactive configuration setup
- `casecraft generate <source>` - Generate test cases from API docs

**Key Options:**
- `--include-tag`, `--exclude-tag` - Filter by API tags
- `--include-path` - Filter by path patterns  
- `--workers N` - Worker control (BigModel only supports 1)
- `--force` - Force regeneration of all endpoints
- `--dry-run` - Preview mode without LLM calls
- `--quiet`, `-q` - Quiet mode (only warnings and errors)
- `--verbose`, `-v` - Verbose mode (includes DEBUG level logs)

## Implementation Notes

This is a complete implementation of the requirements defined in `需求文档.md`. All core MVP functionality has been implemented:

✅ **Multi-format API parsing** (OpenAPI 3.0, Swagger 2.0)
✅ **LLM-powered test generation** (BigModel GLM-4.5-X)  
✅ **Incremental processing** (change detection, state management)
✅ **Sequential execution optimized for BigModel**
✅ **Rich CLI interface** (progress tracking, error handling)
✅ **Comprehensive testing** (unit, integration, CLI tests)

The architecture supports future extensions like direct test code generation and Postman collection export through the modular design of formatters and output managers.

## Version Management

### Git Commit Guidelines

When making commits to this project, follow these practices:

1. **Commit Message Format**
   ```
   <type>: <subject>
   
   <body>
   
   <footer>
   ```

2. **Commit Types**
   - `feat`: New feature
   - `fix`: Bug fix
   - `docs`: Documentation changes
   - `style`: Code style changes (formatting, etc.)
   - `refactor`: Code refactoring
   - `test`: Test additions or modifications
   - `chore`: Maintenance tasks

3. **Version Tagging**
   - Use semantic versioning: `MAJOR.MINOR.PATCH`
   - Tag releases: `git tag -a v1.0.0 -m "Release version 1.0.0"`
   - Major version: Breaking changes
   - Minor version: New features (backward compatible)
   - Patch version: Bug fixes

4. **Branch Strategy**
   - `main`: Stable, production-ready code
   - `develop`: Integration branch for features
   - `feature/*`: Individual feature development
   - `bugfix/*`: Bug fix branches
   - `release/*`: Release preparation

5. **Important Notes**
   - Always commit with clear, descriptive messages
   - Include issue numbers when applicable: `fix: resolve API parsing error #123`
   - Keep commits atomic (one logical change per commit)
   - Never commit sensitive data (API keys, credentials)
   - **DO NOT** include AI assistance attribution in commit messages
   - Avoid adding `Co-Authored-By: Claude` or similar AI attribution lines
   - Keep commit messages clean and professional without AI-generated footers

### Recent Major Changes

- **v0.5.0**: Non-streaming progress bar support and streaming optimization (2025-08-07)
  - Implemented smart progress simulation for non-streaming mode (10% → 80% → 90% → 100%)
  - Added logarithmic progress curve for realistic user experience
  - Implemented retry rollback mechanism (30% rollback, minimum 10%)
  - Unified progress bar interaction for both streaming and non-streaming modes
- **v0.4.0**: Enhanced logging and authentication placeholders (2025-08-07)
  - Implemented automatic `.env` file loading for configuration
  - Added `--quiet` and `--verbose` CLI options for output control
  - Optimized terminal logging display with timestamps and level labels
  - Updated authentication placeholders to environment variable style (`${AUTH_TOKEN}`, `${API_KEY}`, etc.)
- **v0.3.0**: Reorganized core module into functional sub-packages (parsing, generation, management)
- **v0.2.0**: Renamed `BigModelClient` to `LLMClient` for future extensibility
- **v0.1.0**: Initial MVP release with BigModel GLM-4.5-X support

### Git Push Instructions

When pushing to GitHub, use the following commands:

```bash
# Set remote URL with GitHub token
git remote set-url origin https://<GITHUB_TOKEN>@github.com/Devliang24/casecraft.git

# Example with placeholder token (DO NOT commit real tokens to the repo):
# git remote set-url origin https://ghp_YOUR_GITHUB_TOKEN_HERE@github.com/Devliang24/casecraft.git

# Push to remote
git push origin main
```

**Important**: Never commit GitHub tokens to the repository. Store them securely and use environment variables or temporary authentication.