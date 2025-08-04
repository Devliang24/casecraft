"""Exception handling utilities for CaseCraft."""

import traceback
from typing import Any, Dict, List, Optional, Type, Union

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


class CaseCraftError(Exception):
    """Base exception for CaseCraft errors."""
    
    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        suggestion: Optional[str] = None,
        error_code: Optional[str] = None
    ):
        """Initialize CaseCraft error.
        
        Args:
            message: Error message
            details: Additional error details
            suggestion: Suggestion for fixing the error
            error_code: Error code for categorization
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.suggestion = suggestion
        self.error_code = error_code
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary.
        
        Returns:
            Error dictionary representation
        """
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
            "suggestion": self.suggestion,
            "error_code": self.error_code
        }


class ConfigurationError(CaseCraftError):
    """Configuration related errors."""
    pass


class APIDocumentationError(CaseCraftError):
    """API documentation parsing errors."""
    pass


class LLMServiceError(CaseCraftError):
    """LLM service related errors."""
    pass


class TestGenerationError(CaseCraftError):
    """Test case generation errors."""
    pass


class FileOperationError(CaseCraftError):
    """File operation errors."""
    pass


class NetworkError(CaseCraftError):
    """Network related errors."""
    pass


class ValidationError(CaseCraftError):
    """Data validation errors."""
    pass


class ConcurrencyError(CaseCraftError):
    """Concurrency related errors."""
    pass


class ErrorHandler:
    """Centralized error handling and reporting."""
    
    def __init__(self, console: Optional[Console] = None, verbose: bool = False):
        """Initialize error handler.
        
        Args:
            console: Rich console for output
            verbose: Enable verbose error reporting
        """
        self.console = console or Console()
        self.verbose = verbose
        self.error_counts: Dict[str, int] = {}
    
    def handle_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        show_traceback: Optional[bool] = None
    ) -> None:
        """Handle and display error.
        
        Args:
            error: Exception to handle
            context: Additional context information
            show_traceback: Whether to show traceback (defaults to verbose setting)
        """
        # Count error types
        error_type = type(error).__name__
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        
        # Determine if we should show traceback
        if show_traceback is None:
            show_traceback = self.verbose
        
        # Handle CaseCraft errors specially
        if isinstance(error, CaseCraftError):
            self._handle_casecraft_error(error, context, show_traceback)
        else:
            self._handle_generic_error(error, context, show_traceback)
    
    def _handle_casecraft_error(
        self,
        error: CaseCraftError,
        context: Optional[Dict[str, Any]],
        show_traceback: bool
    ) -> None:
        """Handle CaseCraft-specific errors.
        
        Args:
            error: CaseCraft error
            context: Additional context
            show_traceback: Whether to show traceback
        """
        # Create error panel
        error_content = []
        
        # Error message
        error_content.append(f"[red]{error.message}[/red]")
        
        # Error details
        if error.details:
            error_content.append("")
            error_content.append("[bold]Details:[/bold]")
            for key, value in error.details.items():
                error_content.append(f"  {key}: {value}")
        
        # Additional context
        if context:
            error_content.append("")
            error_content.append("[bold]Context:[/bold]")
            for key, value in context.items():
                error_content.append(f"  {key}: {value}")
        
        # Suggestion
        if error.suggestion:
            error_content.append("")
            error_content.append(f"[yellow]💡 Suggestion: {error.suggestion}[/yellow]")
        
        # Show panel
        panel_title = f"{type(error).__name__}"
        if error.error_code:
            panel_title += f" ({error.error_code})"
        
        self.console.print(Panel(
            "\n".join(error_content),
            title=panel_title,
            border_style="red"
        ))
        
        # Show traceback if requested
        if show_traceback:
            self.console.print("\n[dim]Traceback:[/dim]")
            self.console.print_exception(show_locals=True)
    
    def _handle_generic_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]],
        show_traceback: bool
    ) -> None:
        """Handle generic Python errors.
        
        Args:
            error: Generic exception
            context: Additional context
            show_traceback: Whether to show traceback
        """
        error_content = []
        
        # Error message
        error_content.append(f"[red]{str(error)}[/red]")
        
        # Context
        if context:
            error_content.append("")
            error_content.append("[bold]Context:[/bold]")
            for key, value in context.items():
                error_content.append(f"  {key}: {value}")
        
        # Show panel
        self.console.print(Panel(
            "\n".join(error_content),
            title=type(error).__name__,
            border_style="red"
        ))
        
        # Show traceback if requested
        if show_traceback:
            self.console.print("\n[dim]Traceback:[/dim]")
            self.console.print_exception(show_locals=True)
    
    def get_error_summary(self) -> Dict[str, int]:
        """Get summary of handled errors.
        
        Returns:
            Dictionary mapping error types to counts
        """
        return self.error_counts.copy()
    
    def show_error_summary(self) -> None:
        """Display error summary table."""
        if not self.error_counts:
            return
        
        table = Table(title="Error Summary", show_header=True, header_style="bold magenta")
        table.add_column("Error Type", style="cyan")
        table.add_column("Count", justify="right", style="red")
        
        for error_type, count in sorted(self.error_counts.items()):
            table.add_row(error_type, str(count))
        
        self.console.print(table)
    
    def clear_error_counts(self) -> None:
        """Clear error count tracking."""
        self.error_counts.clear()


class RetryableError(CaseCraftError):
    """Error that can be retried."""
    
    def __init__(
        self,
        message: str,
        retry_after: Optional[float] = None,
        max_retries: Optional[int] = None,
        **kwargs
    ):
        """Initialize retryable error.
        
        Args:
            message: Error message
            retry_after: Suggested retry delay in seconds
            max_retries: Maximum number of retries
            **kwargs: Additional arguments for CaseCraftError
        """
        super().__init__(message, **kwargs)
        self.retry_after = retry_after
        self.max_retries = max_retries


class ErrorContext:
    """Context manager for error handling."""
    
    def __init__(
        self,
        handler: ErrorHandler,
        operation: str,
        **context
    ):
        """Initialize error context.
        
        Args:
            handler: Error handler instance
            operation: Operation being performed
            **context: Additional context
        """
        self.handler = handler
        self.operation = operation
        self.context = {"operation": operation, **context}
    
    def __enter__(self) -> "ErrorContext":
        """Enter error context."""
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        """Handle any exception that occurred."""
        if exc_type is not None:
            self.handler.handle_error(exc_value, self.context)
        
        # Don't suppress exceptions
        return False


def convert_exception_to_casecraft_error(
    exc: Exception,
    operation: str,
    suggestion: Optional[str] = None
) -> CaseCraftError:
    """Convert generic exception to CaseCraft error.
    
    Args:
        exc: Original exception
        operation: Operation that caused the error
        suggestion: Optional suggestion for fixing
        
    Returns:
        CaseCraft error with appropriate type
    """
    # Map common exception types to CaseCraft errors
    error_mapping = {
        OSError: FileOperationError,
        IOError: FileOperationError,
        PermissionError: FileOperationError,
        FileNotFoundError: FileOperationError,
        ConnectionError: NetworkError,
        TimeoutError: NetworkError,
        ValueError: ValidationError,
        TypeError: ValidationError,
    }
    
    # Get appropriate CaseCraft error class
    casecraft_error_class = error_mapping.get(type(exc), CaseCraftError)
    
    # Create error with context
    return casecraft_error_class(
        message=f"{operation} failed: {str(exc)}",
        details={
            "original_exception": type(exc).__name__,
            "original_message": str(exc),
            "operation": operation
        },
        suggestion=suggestion
    )


def safe_execute(
    func,
    *args,
    error_handler: Optional[ErrorHandler] = None,
    operation: Optional[str] = None,
    **kwargs
) -> Any:
    """Safely execute function with error handling.
    
    Args:
        func: Function to execute
        *args: Function arguments
        error_handler: Optional error handler
        operation: Operation description
        **kwargs: Function keyword arguments
        
    Returns:
        Function result or None if error occurred
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if error_handler:
            context = {"operation": operation} if operation else None
            error_handler.handle_error(e, context)
        else:
            # Re-raise if no handler provided
            raise
        return None


def create_error_suggestions() -> Dict[Type[Exception], str]:
    """Create mapping of exceptions to user-friendly suggestions.
    
    Returns:
        Dictionary mapping exception types to suggestions
    """
    return {
        FileNotFoundError: "Check that the file path is correct and the file exists",
        PermissionError: "Check file permissions and ensure you have read/write access",
        ConnectionError: "Check your internet connection and try again",
        TimeoutError: "The operation timed out. Try increasing the timeout or check network connectivity",
        ValueError: "Check that all input values are valid and in the correct format",
        KeyError: "Check that all required configuration keys are present",
        ImportError: "Ensure all required dependencies are installed",
    }