# CaseCraft Development Makefile

.PHONY: help install install-dev test test-unit test-integration lint format type-check clean build docs run-example

# Default target
help:
	@echo "CaseCraft Development Commands"
	@echo "============================="
	@echo ""
	@echo "Setup:"
	@echo "  install          Install CaseCraft for production use"
	@echo "  install-dev      Install CaseCraft with development dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  test             Run all tests"
	@echo "  test-unit        Run unit tests only"
	@echo "  test-integration Run integration tests only"
	@echo "  test-cov         Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint             Run linting (ruff)"
	@echo "  format           Format code (black)"
	@echo "  type-check       Run type checking (mypy)"
	@echo "  quality          Run all quality checks"
	@echo ""
	@echo "Development:"
	@echo "  clean            Clean build artifacts"
	@echo "  build            Build distribution packages"
	@echo "  docs             Generate documentation"
	@echo "  run-example      Run example with sample API"
	@echo ""

# Installation
install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"
	pre-commit install

# Testing
test:
	pytest

test-unit:
	pytest tests/unit/ -v

test-integration:
	pytest tests/integration/ -v

test-cov:
	pytest --cov=casecraft --cov-report=html --cov-report=term-missing

# Code Quality
lint:
	ruff check casecraft tests

format:
	black casecraft tests

type-check:
	mypy casecraft

quality: lint type-check
	@echo "All quality checks passed!"

# Development
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build: clean
	python -m build

docs:
	@echo "Documentation generation not implemented yet"

run-example:
	@echo "Running CaseCraft with Petstore API example..."
	casecraft generate https://petstore.swagger.io/v2/swagger.json --dry-run

# Development server for testing
dev-server:
	@echo "Starting development environment..."
	@echo "Run 'make install-dev' first if you haven't already"

# Continuous integration targets
ci-test: install-dev test-cov quality
	@echo "CI tests completed"

# Release preparation
pre-release: clean quality test
	@echo "Pre-release checks completed"
	python -m build
	@echo "Distribution packages built"

# Quick development setup
dev-setup: install-dev
	@echo "Development environment ready!"
	@echo "Run 'casecraft init' to get started"