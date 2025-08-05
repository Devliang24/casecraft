"""Tests for error handling utilities."""

import pytest
from unittest.mock import Mock

from casecraft.utils.exceptions import (
    CaseCraftError, ConfigurationError, ErrorHandler, 
    ErrorContext, RetryableError, convert_exception_to_casecraft_error
)


class TestCaseCraftError:
    """Test CaseCraft error classes."""
    
    def test_basic_error(self):
        """Test basic error creation."""
        error = CaseCraftError("Test error")
        
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.details == {}
        assert error.suggestion is None
        assert error.error_code is None
    
    def test_error_with_details(self):
        """Test error with additional details."""
        error = CaseCraftError(
            "Test error",
            details={"key": "value", "count": 42},
            suggestion="Try fixing this",
            error_code="CC001"
        )
        
        assert error.details["key"] == "value"
        assert error.details["count"] == 42
        assert error.suggestion == "Try fixing this"
        assert error.error_code == "CC001"
    
    def test_error_to_dict(self):
        """Test error serialization to dictionary."""
        error = ConfigurationError(
            "Config missing",
            details={"file": "config.yaml"},
            suggestion="Run casecraft init"
        )
        
        error_dict = error.to_dict()
        
        assert error_dict["error_type"] == "ConfigurationError"
        assert error_dict["message"] == "Config missing"
        assert error_dict["details"]["file"] == "config.yaml"
        assert error_dict["suggestion"] == "Run casecraft init"


class TestRetryableError:
    """Test retryable error functionality."""
    
    def test_retryable_error(self):
        """Test retryable error creation."""
        error = RetryableError(
            "Temporary failure",
            retry_after=5.0,
            max_retries=3
        )
        
        assert error.retry_after == 5.0
        assert error.max_retries == 3
        assert str(error) == "Temporary failure"


class TestErrorHandler:
    """Test error handler functionality."""
    
    def test_init(self):
        """Test error handler initialization."""
        console = Mock()
        handler = ErrorHandler(console, verbose=True)
        
        assert handler.console == console
        assert handler.verbose is True
        assert handler.error_counts == {}
    
    def test_handle_casecraft_error(self):
        """Test handling CaseCraft errors."""
        console = Mock()
        handler = ErrorHandler(console, verbose=False)
        
        error = CaseCraftError(
            "Test error",
            details={"test": "value"},
            suggestion="Fix it"
        )
        
        handler.handle_error(error)
        
        # Check error was counted
        assert handler.error_counts["CaseCraftError"] == 1
        
        # Check console was called
        console.print.assert_called()
    
    def test_handle_generic_error(self):
        """Test handling generic Python errors."""
        console = Mock()
        handler = ErrorHandler(console, verbose=False)
        
        error = ValueError("Invalid value")
        context = {"operation": "test"}
        
        handler.handle_error(error, context)
        
        # Check error was counted
        assert handler.error_counts["ValueError"] == 1
        
        # Check console was called
        console.print.assert_called()
    
    def test_error_counting(self):
        """Test error counting functionality."""
        console = Mock()
        handler = ErrorHandler(console)
        
        # Handle multiple errors
        handler.handle_error(ValueError("Error 1"))
        handler.handle_error(ValueError("Error 2"))
        handler.handle_error(TypeError("Error 3"))
        
        summary = handler.get_error_summary()
        
        assert summary["ValueError"] == 2
        assert summary["TypeError"] == 1
    
    def test_clear_error_counts(self):
        """Test clearing error counts."""
        console = Mock()
        handler = ErrorHandler(console)
        
        handler.handle_error(ValueError("Error"))
        assert len(handler.error_counts) > 0
        
        handler.clear_error_counts()
        assert len(handler.error_counts) == 0
    
    def test_show_error_summary(self):
        """Test error summary display."""
        console = Mock()
        handler = ErrorHandler(console)
        
        # No errors - should not print
        handler.show_error_summary()
        console.print.assert_not_called()
        
        # With errors - should print table
        handler.handle_error(ValueError("Error"))
        console.reset_mock()
        
        handler.show_error_summary()
        console.print.assert_called()


class TestErrorContext:
    """Test error context manager."""
    
    def test_error_context_success(self):
        """Test error context with successful operation."""
        handler = Mock()
        
        with ErrorContext(handler, "test_operation") as ctx:
            # Successful operation
            pass
        
        # Handler should not be called for success
        handler.handle_error.assert_not_called()
    
    def test_error_context_with_exception(self):
        """Test error context with exception."""
        handler = Mock()
        
        test_error = ValueError("Test error")
        
        with pytest.raises(ValueError):
            with ErrorContext(handler, "test_operation", extra="context"):
                raise test_error
        
        # Handler should be called with error and context
        handler.handle_error.assert_called_once()
        args = handler.handle_error.call_args
        
        assert args[0][0] == test_error
        assert args[0][1]["operation"] == "test_operation"
        assert args[0][1]["extra"] == "context"


class TestExceptionConversion:
    """Test exception conversion utilities."""
    
    def test_convert_file_error(self):
        """Test converting file-related errors."""
        original = FileNotFoundError("File not found")
        converted = convert_exception_to_casecraft_error(
            original, 
            "reading config",
            "Check file path"
        )
        
        assert "reading config failed" in converted.message
        assert converted.details["original_exception"] == "FileNotFoundError"
        assert converted.suggestion == "Check file path"
    
    def test_convert_generic_error(self):
        """Test converting generic errors."""
        original = RuntimeError("Something went wrong")
        converted = convert_exception_to_casecraft_error(
            original,
            "processing data"
        )
        
        assert isinstance(converted, CaseCraftError)
        assert "processing data failed" in converted.message
        assert converted.details["original_exception"] == "RuntimeError"
    
    def test_convert_network_error(self):
        """Test converting network errors."""
        original = ConnectionError("Connection failed")
        converted = convert_exception_to_casecraft_error(
            original,
            "API call"
        )
        
        # Should be converted to NetworkError due to mapping
        from casecraft.utils.exceptions import NetworkError
        assert isinstance(converted, NetworkError)
        assert "API call failed" in converted.message


class TestSafeExecute:
    """Test safe execution utility."""
    
    def test_safe_execute_success(self):
        """Test safe execution with successful function."""
        from casecraft.utils.exceptions import safe_execute
        
        def test_func(x, y):
            return x + y
        
        result = safe_execute(test_func, 2, 3)
        assert result == 5
    
    def test_safe_execute_with_error_handler(self):
        """Test safe execution with error handler."""
        from casecraft.utils.exceptions import safe_execute
        
        handler = Mock()
        
        def failing_func():
            raise ValueError("Test error")
        
        result = safe_execute(
            failing_func,
            error_handler=handler,
            operation="test"
        )
        
        assert result is None
        handler.handle_error.assert_called_once()
    
    def test_safe_execute_without_handler(self):
        """Test safe execution without error handler."""
        from casecraft.utils.exceptions import safe_execute
        
        def failing_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            safe_execute(failing_func)


class TestErrorSuggestions:
    """Test error suggestion mapping."""
    
    def test_create_error_suggestions(self):
        """Test error suggestion creation."""
        from casecraft.utils.exceptions import create_error_suggestions
        
        suggestions = create_error_suggestions()
        
        assert isinstance(suggestions, dict)
        assert FileNotFoundError in suggestions
        assert PermissionError in suggestions
        assert ConnectionError in suggestions
        
        # Check suggestions are strings
        for suggestion in suggestions.values():
            assert isinstance(suggestion, str)
            assert len(suggestion) > 0