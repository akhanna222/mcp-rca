"""Custom exceptions for the RCA platform."""


class RCAException(Exception):
    """Base exception for all RCA platform errors."""

    def __init__(self, message: str, details: dict = None):
        """Initialize exception with message and optional details.

        Args:
            message: Human-readable error message
            details: Additional context about the error
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        """String representation of the exception."""
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class ConfigurationError(RCAException):
    """Raised when there's an issue with configuration."""

    pass


class AuthenticationError(RCAException):
    """Raised when authentication fails."""

    pass


class MonitoringError(RCAException):
    """Raised when monitoring data retrieval fails."""

    pass


class LoggingError(RCAException):
    """Raised when log data retrieval fails."""

    pass


class MCPError(RCAException):
    """Raised when MCP communication fails."""

    pass


class AlertProcessingError(RCAException):
    """Raised when alert processing fails."""

    pass
