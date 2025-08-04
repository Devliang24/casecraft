# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CaseCraft** is a CLI tool for API testing that parses API documentation (OpenAPI/Swagger) and uses BigModel LLM to generate structured test case data in JSON format.

## Core Architecture Requirements

### Command Structure
- `casecraft init` - Initialize configuration with secure API key storage in `~/.casecraft/config.yaml`
- `casecraft generate <source>` - Generate test cases from API docs (URL or local file)
- Support for filtering: `--include-tag`, `--exclude-tag`, `--include-path`
- Concurrent processing: `--workers N`
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
Each generated test case must include:
- At least two successful positive cases
- At least three different negative cases (missing required fields, type errors, format errors)
- Boundary value testing for numeric/length constraints

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

**Configuration Management (`casecraft/core/config_manager.py`)**
- Handles secure API key storage in `~/.casecraft/config.yaml`
- Supports environment variable overrides (`CASECRAFT_*`)
- Configuration priority: CLI args > env vars > config file

**API Documentation Processing (`casecraft/core/api_parser.py`)**
- Supports OpenAPI 3.0 and Swagger 2.0 (JSON/YAML)
- Loads from URLs and local file system  
- Advanced filtering by tags and path patterns

**LLM Integration (`casecraft/core/llm_client.py`)**
- BigModel GLM-4.5-X client implementation with single concurrency
- Built-in rate limiting and retry logic for HTTP 429 errors
- Structured error handling for different failure modes

**Test Case Generation (`casecraft/core/test_generator.py`)**
- Single LLM call per API endpoint generates all test cases
- Enforces coverage requirements (2+ positive, 3+ negative, boundary cases)
- JSON schema validation for generated test cases

**Incremental Generation (`casecraft/core/state_manager.py`)**
- Tracks API changes in `.casecraft_state.json`
- Skip unchanged endpoints to avoid unnecessary LLM calls
- Content-based hashing for change detection

**Output Management (`casecraft/core/output_manager.py`)**
- JSON format output (one file per API endpoint)
- Optional organization by tag into subdirectories
- File naming templates and conflict resolution

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

### Recent Major Changes

- **v0.2.0**: Renamed `BigModelClient` to `LLMClient` for future extensibility
- **v0.1.0**: Initial MVP release with BigModel GLM-4.5-X support