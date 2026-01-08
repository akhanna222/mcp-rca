"""Base observability server for MCP.

This module defines the abstract base class for observability servers
that integrate with cloud monitoring and logging services.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.models.config import ProjectConfig


class ObservabilityServer(ABC):
    """Abstract base class for cloud observability servers.

    Provides a common interface for querying monitoring data and logs
    from different cloud providers.
    """

    def __init__(self, project_config: ProjectConfig):
        """Initialize observability server.

        Args:
            project_config: Project configuration
        """
        self.project_config = project_config
        self.project_name = project_config.name
        self.provider = project_config.provider

    @abstractmethod
    async def query_metrics(
        self,
        queries: List[tuple[str, str]],
        timeout: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Query monitoring metrics.

        Args:
            queries: List of (query_string, purpose) tuples
            timeout: Optional timeout in seconds

        Returns:
            List of metric results with purpose and data
        """
        pass

    @abstractmethod
    async def query_logs(
        self,
        filter_query: str,
        time_range_minutes: float,
        order_by: str = "timestamp asc",
        max_entries: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Query logs.

        Args:
            filter_query: Log filter query
            time_range_minutes: Time range in minutes
            order_by: Sort order
            max_entries: Maximum log entries to return

        Returns:
            List of log entries
        """
        pass

    @abstractmethod
    async def authenticate(self) -> None:
        """Authenticate with the cloud provider.

        Raises:
            AuthenticationError: If authentication fails
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the observability service is accessible.

        Returns:
            True if service is healthy
        """
        pass
