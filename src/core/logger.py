"""Structured logging module for the RCA platform.

This module provides production-grade logging with:
- Structured JSON logging
- Context injection
- Performance tracking
- Correlation IDs for distributed tracing
"""

import asyncio
import json
import logging
import sys
import time
from contextvars import ContextVar
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Context variables for request tracking
correlation_id_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
project_name_var: ContextVar[Optional[str]] = ContextVar("project_name", default=None)


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log string
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add correlation ID if present
        correlation_id = correlation_id_var.get()
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        # Add project name if present
        project_name = project_name_var.get()
        if project_name:
            log_data["project"] = project_name

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add any extra fields
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """Human-readable text formatter."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as readable text.

        Args:
            record: Log record to format

        Returns:
            Formatted log string
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        correlation_id = correlation_id_var.get()
        project_name = project_name_var.get()

        parts = [f"[{timestamp}]", f"[{record.levelname}]"]

        if correlation_id:
            parts.append(f"[{correlation_id[:8]}]")

        if project_name:
            parts.append(f"[{project_name}]")

        parts.append(f"{record.name}:{record.funcName}:{record.lineno}")
        parts.append("-")
        parts.append(record.getMessage())

        return " ".join(parts)


class RCALogger(logging.LoggerAdapter):
    """Custom logger adapter with extra context support."""

    def __init__(self, logger: logging.Logger, extra: Dict[str, Any] = None):
        """Initialize logger adapter.

        Args:
            logger: Base logger instance
            extra: Extra context to include in all logs
        """
        super().__init__(logger, extra or {})

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """Process log message to add extra context.

        Args:
            msg: Log message
            kwargs: Keyword arguments

        Returns:
            Processed message and kwargs
        """
        # Add extra fields to the record
        if "extra" not in kwargs:
            kwargs["extra"] = {}

        kwargs["extra"]["extra_fields"] = {**self.extra, **kwargs["extra"]}

        return msg, kwargs

    def with_context(self, **kwargs: Any) -> "RCALogger":
        """Create a new logger with additional context.

        Args:
            **kwargs: Additional context fields

        Returns:
            New logger instance with added context
        """
        new_extra = {**self.extra, **kwargs}
        return RCALogger(self.logger, new_extra)


def setup_logging(
    level: str = "INFO",
    log_format: str = "json",
    log_file: Optional[Path] = None,
) -> None:
    """Setup logging configuration for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Format type (json or text)
        log_file: Optional file path for logging
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Create formatter based on format type
    if log_format == "json":
        formatter = StructuredFormatter()
    else:
        formatter = TextFormatter()

    # Setup handlers
    handlers = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

    # File handler if specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        handlers=handlers,
        force=True,  # Override any existing configuration
    )

    # Reduce noise from third-party libraries
    logging.getLogger("anthropic").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str, **extra_context: Any) -> RCALogger:
    """Get a logger instance with optional extra context.

    Args:
        name: Logger name (typically __name__)
        **extra_context: Additional context to include in all logs

    Returns:
        RCALogger instance
    """
    base_logger = logging.getLogger(name)
    return RCALogger(base_logger, extra_context)


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID for current context.

    Args:
        correlation_id: Unique identifier for request tracing
    """
    correlation_id_var.set(correlation_id)


def get_correlation_id() -> Optional[str]:
    """Get current correlation ID.

    Returns:
        Current correlation ID or None
    """
    return correlation_id_var.get()


def set_project_context(project_name: str) -> None:
    """Set project name for current context.

    Args:
        project_name: Name of the project being processed
    """
    project_name_var.set(project_name)


def clear_context() -> None:
    """Clear all context variables."""
    correlation_id_var.set(None)
    project_name_var.set(None)


def log_execution_time(logger: Optional[RCALogger] = None) -> Callable:
    """Decorator to log function execution time.

    Args:
        logger: Logger instance (uses function's module logger if not provided)

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal logger
            if logger is None:
                logger = get_logger(func.__module__)

            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.info(
                    f"Function {func.__name__} completed",
                    extra={"execution_time_seconds": execution_time}
                )
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(
                    f"Function {func.__name__} failed",
                    extra={
                        "execution_time_seconds": execution_time,
                        "error": str(e)
                    },
                    exc_info=True
                )
                raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal logger
            if logger is None:
                logger = get_logger(func.__module__)

            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.info(
                    f"Function {func.__name__} completed",
                    extra={"execution_time_seconds": execution_time}
                )
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(
                    f"Function {func.__name__} failed",
                    extra={
                        "execution_time_seconds": execution_time,
                        "error": str(e)
                    },
                    exc_info=True
                )
                raise

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
