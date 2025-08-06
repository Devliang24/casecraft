"""Structured logging utilities for CaseCraft."""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

import structlog
from rich.console import Console
from rich.logging import RichHandler


def configure_logging(
    log_level: str = "INFO",
    log_file: Optional[Union[str, Path]] = None,
    verbose: bool = False,
    structured: bool = True
) -> None:
    """Configure structured logging for CaseCraft.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Optional log file path
        verbose: Enable verbose output
        structured: Use structured logging format
    """
    # Configure structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="ISO"),
    ]
    
    if structured:
        processors.extend([
            structlog.processors.JSONRenderer()
        ])
    else:
        processors.extend([
            structlog.dev.ConsoleRenderer(colors=True)
        ])
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(structlog.stdlib, log_level.upper(), structlog.INFO)
        ),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Set up file logging if requested
    if log_file:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)


def get_logger(name: str = "casecraft") -> structlog.BoundLogger:
    """Get a structured logger instance.
    
    Args:
        name: Logger name
        
    Returns:
        Configured logger instance
    """
    return structlog.get_logger(name)


class CaseCraftLogger:
    """Enhanced logger with CaseCraft-specific functionality."""
    
    def __init__(
        self,
        name: str = "casecraft",
        console: Optional[Console] = None,
        verbose: bool = False
    ):
        """Initialize CaseCraft logger.
        
        Args:
            name: Logger name
            console: Rich console for output
            verbose: Enable verbose output
        """
        self.name = name
        self.logger = get_logger(name)
        self.console = console or Console()
        self.verbose = verbose
        self._context: Dict[str, Any] = {}
    
    def bind(self, **kwargs) -> "CaseCraftLogger":
        """Bind context variables to logger.
        
        Args:
            **kwargs: Context variables to bind
            
        Returns:
            New logger instance with bound context
        """
        new_logger = CaseCraftLogger(
            name=self.name,
            console=self.console,
            verbose=self.verbose
        )
        new_logger.logger = self.logger.bind(**kwargs)
        new_logger._context = {**self._context, **kwargs}
        return new_logger
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        if self.verbose:
            self.console.print(f"[dim]DEBUG: {message}[/dim]")
        self.logger.debug(message, **kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self.logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self.console.print(f"[yellow]WARNING: {message}[/yellow]")
        self.logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        self.console.print(f"[red]ERROR: {message}[/red]")
        self.logger.error(message, **kwargs)
    
    def success(self, message: str, **kwargs) -> None:
        """Log success message."""
        self.console.print(f"[green]✓ {message}[/green]")
        self.logger.info(f"SUCCESS: {message}", **kwargs)
    
    def progress(self, message: str, **kwargs) -> None:
        """Log progress message."""
        self.console.print(f"[blue]→ {message}[/blue]")
        self.logger.info(f"PROGRESS: {message}", **kwargs)
    
    def log_operation_start(self, operation: str, **context) -> "CaseCraftLogger":
        """Log operation start with context.
        
        Args:
            operation: Operation name
            **context: Additional context
            
        Returns:
            Logger bound with operation context
        """
        operation_logger = self.bind(
            operation=operation,
            operation_start=datetime.now().isoformat(),
            **context
        )
        operation_logger.info(f"Starting {operation}")
        return operation_logger
    
    def log_operation_end(
        self,
        operation: str,
        success: bool = True,
        duration: Optional[float] = None,
        **context
    ) -> None:
        """Log operation completion.
        
        Args:
            operation: Operation name
            success: Whether operation succeeded
            duration: Operation duration in seconds
            **context: Additional context
        """
        status = "completed" if success else "failed"
        message = f"Operation {operation} {status}"
        
        log_context = {
            "operation": operation,
            "success": success,
            "operation_end": datetime.now().isoformat(),
            **context
        }
        
        if duration is not None:
            log_context["duration_seconds"] = duration
            message += f" in {duration:.2f}s"
        
        if success:
            self.success(message, **log_context)
        else:
            self.error(message, **log_context)
    
    def log_api_call(
        self,
        method: str,
        endpoint: str,
        status_code: Optional[int] = None,
        duration: Optional[float] = None,
        **context
    ) -> None:
        """Log API call details.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            status_code: Response status code
            duration: Call duration in seconds
            **context: Additional context
        """
        log_context = {
            "api_method": method,
            "api_endpoint": endpoint,
            **context
        }
        
        if status_code is not None:
            log_context["status_code"] = status_code
        
        if duration is not None:
            log_context["duration_seconds"] = duration
        
        message = f"API call {method} {endpoint}"
        if status_code:
            message += f" -> {status_code}"
        
        self.info(message, **log_context)
    
    def log_llm_generation(
        self,
        endpoint: str,
        model: str,
        tokens_used: Optional[int] = None,
        duration: Optional[float] = None,
        success: bool = True,
        **context
    ) -> None:
        """Log LLM generation details.
        
        Args:
            endpoint: API endpoint being processed
            model: LLM model used
            tokens_used: Number of tokens consumed
            duration: Generation duration
            success: Whether generation succeeded
            **context: Additional context
        """
        log_context = {
            "llm_model": model,
            "endpoint": endpoint,
            "llm_success": success,
            **context
        }
        
        if tokens_used is not None:
            log_context["tokens_used"] = tokens_used
        
        if duration is not None:
            log_context["duration_seconds"] = duration
        
        message = f"LLM generation for {endpoint} using {model}"
        if tokens_used:
            message += f" ({tokens_used} tokens)"
        
        if success:
            self.info(message, **log_context)
        else:
            self.error(f"Failed: {message}", **log_context)
    
    def log_file_operation(
        self,
        operation: str,
        file_path: Union[str, Path],
        file_size: Optional[int] = None,
        success: bool = True,
        **context
    ) -> None:
        """Log file operation.
        
        Args:
            operation: Operation type (read, write, delete)
            file_path: File path
            file_size: File size in bytes
            success: Whether operation succeeded
            **context: Additional context
        """
        log_context = {
            "file_operation": operation,
            "file_path": str(file_path),
            "file_success": success,
            **context
        }
        
        if file_size is not None:
            log_context["file_size_bytes"] = file_size
        
        message = f"File {operation}: {file_path}"
        if file_size:
            message += f" ({file_size} bytes)"
        
        if success:
            self.info(message, **log_context)
        else:
            self.error(f"Failed: {message}", **log_context)
    
    def get_context(self) -> Dict[str, Any]:
        """Get current logger context.
        
        Returns:
            Current context dictionary
        """
        return self._context.copy()


def setup_error_tracking(logger: CaseCraftLogger) -> None:
    """Set up error tracking and reporting.
    
    Args:
        logger: Logger instance to enhance
    """
    # Set up global exception handler
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        logger.error(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback),
            exception_type=exc_type.__name__,
            exception_message=str(exc_value)
        )
    
    sys.excepthook = handle_exception


class LoggingContext:
    """Context manager for logging operations."""
    
    def __init__(
        self,
        logger: CaseCraftLogger,
        operation: str,
        **context
    ):
        """Initialize logging context.
        
        Args:
            logger: Logger instance
            operation: Operation name
            **context: Additional context
        """
        self.logger = logger
        self.operation = operation
        self.context = context
        self.start_time: Optional[float] = None
        self.operation_logger: Optional[CaseCraftLogger] = None
        self.manual_success: Optional[bool] = None
    
    def __enter__(self) -> CaseCraftLogger:
        """Enter context and start logging."""
        import time
        self.start_time = time.time()
        self.operation_logger = self.logger.log_operation_start(
            self.operation, **self.context
        )
        return self.operation_logger
    
    def set_success(self, success: bool) -> None:
        """Manually set the success status for this operation.
        
        This overrides the default exception-based success determination.
        
        Args:
            success: Whether the operation should be considered successful
        """
        self.manual_success = success
    
    def __exit__(self, exc_type, exc_value, traceback):
        """Exit context and log completion."""
        import time
        
        if self.start_time is not None:
            duration = time.time() - self.start_time
        else:
            duration = None
        
        # Use manual success if set, otherwise fall back to exception checking
        if self.manual_success is not None:
            success = self.manual_success
        else:
            success = exc_type is None
        
        if self.operation_logger:
            self.operation_logger.log_operation_end(
                self.operation,
                success=success,
                duration=duration,
                **self.context
            )
        
        # Don't suppress exceptions
        return False