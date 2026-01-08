"""Google Cloud Platform observability server.

Production-grade MCP server for querying GCP monitoring and logging services
with comprehensive error handling, retries, and observability.
"""

import asyncio
import datetime
import json
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
from google.auth import default
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
from mcp.server.fastmcp import FastMCP

from src.core.exceptions import AuthenticationError, LoggingError, MonitoringError
from src.core.logger import get_logger, log_execution_time, set_project_context
from src.models.config import GCPConfig, ProjectConfig
from src.mcp_servers.base import ObservabilityServer

logger = get_logger(__name__)


class GCPObservabilityServer(ObservabilityServer):
    """GCP-specific observability server implementation."""

    # API endpoints
    MONITORING_API_BASE = "https://monitoring.googleapis.com/v1"
    LOGGING_API_BASE = "https://logging.googleapis.com/v2"

    # Default timeouts and limits
    DEFAULT_REQUEST_TIMEOUT = 60.0
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY = 1.0

    def __init__(
        self,
        project_config: ProjectConfig,
        mcp_server: Optional[FastMCP] = None
    ):
        """Initialize GCP observability server.

        Args:
            project_config: Project configuration
            mcp_server: Optional FastMCP server instance for tool registration

        Raises:
            ValueError: If project is not configured for GCP
        """
        super().__init__(project_config)

        if not project_config.gcp:
            raise ValueError(f"Project {project_config.name} is not configured for GCP")

        self.gcp_config: GCPConfig = project_config.gcp
        self.project_id = self.gcp_config.project_id

        # Authentication
        self._credentials: Optional[Credentials] = None
        self._auth_token: Optional[str] = None
        self._auth_headers: Dict[str, str] = {}

        # HTTP client with connection pooling
        self._http_client: Optional[httpx.AsyncClient] = None

        # MCP server for tool registration
        self._mcp_server = mcp_server

        # Set project context for logging
        set_project_context(self.project_name)

        logger.info(
            f"Initialized GCP observability server",
            extra={
                "project_id": self.project_id,
                "project_name": self.project_name
            }
        )

    async def authenticate(self) -> None:
        """Authenticate with Google Cloud Platform.

        Raises:
            AuthenticationError: If authentication fails
        """
        try:
            logger.info("Authenticating with GCP")

            auth_config = self.gcp_config.auth

            # Get credentials based on auth method
            if auth_config.service_account_path:
                # Use service account file
                import os
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
                    auth_config.service_account_path
                )
                logger.info("Using service account authentication")

            # Get default credentials
            self._credentials, detected_project = default(
                quota_project_id=auth_config.quota_project_id,
                scopes=auth_config.scopes
            )

            # Refresh credentials to get token
            self._credentials.refresh(Request())
            self._auth_token = self._credentials.token

            # Set up auth headers
            self._auth_headers = {
                "Authorization": f"Bearer {self._auth_token}",
                "Content-Type": "application/json"
            }

            logger.info(
                "GCP authentication successful",
                extra={
                    "project_id": self.project_id,
                    "detected_project": detected_project
                }
            )

        except Exception as e:
            raise AuthenticationError(
                f"Failed to authenticate with GCP",
                {
                    "project_id": self.project_id,
                    "error": str(e)
                }
            ) from e

    async def _ensure_authenticated(self) -> None:
        """Ensure credentials are valid, refresh if needed."""
        if not self._credentials:
            await self.authenticate()
        elif self._credentials.expired:
            logger.info("Refreshing expired GCP credentials")
            self._credentials.refresh(Request())
            self._auth_token = self._credentials.token
            self._auth_headers["Authorization"] = f"Bearer {self._auth_token}"

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling.

        Returns:
            Async HTTP client instance
        """
        if self._http_client is None or self._http_client.is_closed:
            timeout = self.gcp_config.monitoring.timeout_seconds
            self._http_client = httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20
                )
            )
        return self._http_client

    @log_execution_time()
    async def query_metrics(
        self,
        queries: List[Tuple[str, str]],
        timeout: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Query Prometheus-compatible monitoring metrics from GCP.

        Args:
            queries: List of (promql_query, purpose) tuples
            timeout: Optional timeout override

        Returns:
            List of metric results with purpose and data

        Raises:
            MonitoringError: If query execution fails
        """
        await self._ensure_authenticated()

        timeout = timeout or self.gcp_config.monitoring.timeout_seconds
        max_concurrent = self.gcp_config.monitoring.max_concurrent_queries

        logger.info(
            f"Querying {len(queries)} metrics",
            extra={"query_count": len(queries)}
        )

        url = (
            f"{self.MONITORING_API_BASE}/projects/{self.project_id}/"
            f"location/global/prometheus/api/v1/query"
        )

        client = await self._get_http_client()
        results: List[Dict[str, Any]] = []

        # Process queries with concurrency limit
        sem = asyncio.Semaphore(max_concurrent)

        async def query_single_metric(
            query: str,
            purpose: str
        ) -> Optional[Dict[str, Any]]:
            """Query a single metric with retry logic."""
            async with sem:
                for attempt in range(self.DEFAULT_MAX_RETRIES):
                    try:
                        request_body = {"query": query}
                        response = await client.post(
                            url,
                            json=request_body,
                            headers=self._auth_headers
                        )

                        if response.status_code == 200:
                            data = response.json().get("data", {}).get("result", [])
                            logger.debug(
                                f"Metric query successful: {purpose}",
                                extra={"result_count": len(data)}
                            )
                            return {
                                "purpose": purpose,
                                "data": data,
                                "status": "success"
                            }
                        else:
                            logger.warning(
                                f"Metric query failed: {purpose}",
                                extra={
                                    "status_code": response.status_code,
                                    "response": response.text
                                }
                            )
                            if attempt < self.DEFAULT_MAX_RETRIES - 1:
                                await asyncio.sleep(
                                    self.DEFAULT_RETRY_DELAY * (2 ** attempt)
                                )
                            else:
                                return {
                                    "purpose": purpose,
                                    "data": [],
                                    "status": "error",
                                    "error": f"HTTP {response.status_code}"
                                }

                    except Exception as e:
                        logger.error(
                            f"Exception querying metric: {purpose}",
                            extra={"error": str(e)},
                            exc_info=True
                        )
                        if attempt < self.DEFAULT_MAX_RETRIES - 1:
                            await asyncio.sleep(
                                self.DEFAULT_RETRY_DELAY * (2 ** attempt)
                            )
                        else:
                            return {
                                "purpose": purpose,
                                "data": [],
                                "status": "error",
                                "error": str(e)
                            }

        # Execute all queries concurrently
        tasks = [query_single_metric(query, purpose) for query, purpose in queries]
        results = await asyncio.gather(*tasks)

        # Filter out None results
        results = [r for r in results if r is not None]

        logger.info(
            f"Metrics query completed",
            extra={
                "total_queries": len(queries),
                "successful": sum(1 for r in results if r.get("status") == "success"),
                "failed": sum(1 for r in results if r.get("status") == "error")
            }
        )

        return results

    @log_execution_time()
    async def query_logs(
        self,
        filter_query: str,
        time_range_minutes: float,
        order_by: str = "timestamp asc",
        max_entries: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Query logs from GCP Cloud Logging.

        Args:
            filter_query: Cloud Logging filter query
            time_range_minutes: Time range in minutes
            order_by: Sort order for results
            max_entries: Maximum entries to return

        Returns:
            List of parsed log entries

        Raises:
            LoggingError: If log query fails
        """
        await self._ensure_authenticated()

        max_entries = max_entries or self.gcp_config.logging.max_log_entries

        logger.info(
            "Querying logs",
            extra={
                "time_range_minutes": time_range_minutes,
                "filter": filter_query[:100]  # Truncate for logging
            }
        )

        # Build time-bounded filter
        start_time = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(minutes=time_range_minutes)
        )
        time_filter = (
            f' AND timestamp >= "{start_time.strftime("%Y-%m-%dT%H:%M:%SZ")}"'
        )
        complete_filter = filter_query + time_filter

        # API request body
        resource_name = f"projects/{self.project_id}"
        body = {
            "resourceNames": [resource_name],
            "filter": complete_filter,
            "orderBy": order_by,
            "pageSize": min(max_entries, 1000)  # API limit per page
        }

        url = f"{self.LOGGING_API_BASE}/entries:list"
        client = await self._get_http_client()

        log_entries: List[Dict[str, Any]] = []
        seen_locations: Set[Tuple[Optional[str], Optional[int], Optional[str]]] = set()

        try:
            while len(log_entries) < max_entries:
                response = await client.post(
                    url,
                    headers=self._auth_headers,
                    json=body
                )
                response.raise_for_status()
                data = response.json()

                for entry in data.get("entries", []):
                    if len(log_entries) >= max_entries:
                        break

                    # Extract source location for deduplication
                    source_location = entry.get("sourceLocation", {})
                    location_key = (
                        source_location.get("file"),
                        source_location.get("line"),
                        source_location.get("function")
                    ) if source_location else None

                    # Skip duplicates based on source location
                    if location_key and location_key in seen_locations:
                        continue

                    # Extract message from payload
                    message = self._extract_log_message(entry)

                    # Parse and structure the log entry
                    parsed_entry = {
                        "timestamp": entry.get("timestamp"),
                        "severity": entry.get("severity"),
                        "message": message,
                        "labels": entry.get("labels", {}),
                        "resource": entry.get("resource", {}),
                        "sourceLocation": source_location,
                    }

                    log_entries.append(parsed_entry)

                    if location_key:
                        seen_locations.add(location_key)

                # Check for next page
                if "nextPageToken" in data and len(log_entries) < max_entries:
                    body["pageToken"] = data["nextPageToken"]
                else:
                    break

            logger.info(
                f"Logs query completed",
                extra={
                    "entries_retrieved": len(log_entries),
                    "unique_locations": len(seen_locations)
                }
            )

            return log_entries

        except httpx.HTTPStatusError as e:
            raise LoggingError(
                f"Failed to query logs",
                {
                    "project_id": self.project_id,
                    "status_code": e.response.status_code,
                    "error": str(e)
                }
            ) from e

        except Exception as e:
            raise LoggingError(
                f"Failed to query logs",
                {
                    "project_id": self.project_id,
                    "error": str(e)
                }
            ) from e

    @staticmethod
    def _extract_log_message(entry: Dict[str, Any]) -> str:
        """Extract message from log entry payload.

        Args:
            entry: Raw log entry from API

        Returns:
            Extracted message string
        """
        for key in ["textPayload", "jsonPayload", "protoPayload"]:
            if key in entry:
                try:
                    payload = entry[key]
                    return (
                        json.dumps(payload)
                        if isinstance(payload, dict)
                        else str(payload)
                    )
                except Exception:
                    return str(payload)
        return ""

    async def health_check(self) -> bool:
        """Check if GCP monitoring service is accessible.

        Returns:
            True if service is healthy
        """
        try:
            await self._ensure_authenticated()
            # Try a simple query to verify connectivity
            url = f"{self.MONITORING_API_BASE}/projects/{self.project_id}"
            client = await self._get_http_client()
            response = await client.get(url, headers=self._auth_headers)
            return response.status_code == 200

        except Exception as e:
            logger.error(
                "Health check failed",
                extra={"error": str(e)},
                exc_info=True
            )
            return False

    async def close(self) -> None:
        """Close HTTP client and clean up resources."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            logger.info("HTTP client closed")

    def register_tools(self, mcp: FastMCP) -> None:
        """Register MCP tools for this server.

        Args:
            mcp: FastMCP server instance
        """
        project_id = self.project_id
        server_instance = self

        @mcp.tool()
        async def get_gcp_monitoring_data(
            promql_queries: List[List[str]]
        ) -> List[Dict[str, Any]]:
            """Query monitoring metrics from Google Cloud Monitoring.

            Args:
                promql_queries: List of [query_string, purpose] pairs

            Returns:
                List of metric results with purpose and data
            """
            logger.info(
                f"Tool called: get_gcp_monitoring_data",
                extra={"query_count": len(promql_queries)}
            )

            # Convert list of lists to list of tuples
            queries = [(q[0], q[1]) for q in promql_queries]
            return await server_instance.query_metrics(queries)

        @mcp.tool()
        async def get_gcp_logs(
            log_filter: str,
            time_range_minutes: float = 10.0,
            order_by: str = "timestamp asc"
        ) -> List[Dict[str, Any]]:
            """Query logs from Google Cloud Logging.

            Args:
                log_filter: Cloud Logging filter query
                time_range_minutes: Time range in minutes (default: 10)
                order_by: Sort order (default: "timestamp asc")

            Returns:
                List of log entries
            """
            logger.info(
                f"Tool called: get_gcp_logs",
                extra={
                    "time_range_minutes": time_range_minutes,
                    "filter_preview": log_filter[:100]
                }
            )

            return await server_instance.query_logs(
                log_filter,
                time_range_minutes,
                order_by
            )

        logger.info("MCP tools registered for GCP observability")


def create_gcp_mcp_server(project_config: ProjectConfig) -> FastMCP:
    """Factory function to create a GCP observability MCP server.

    Args:
        project_config: Project configuration

    Returns:
        Configured FastMCP server instance
    """
    mcp = FastMCP(f"gcp_observability_{project_config.name}")

    # Create and initialize server
    server = GCPObservabilityServer(project_config, mcp)

    # Register authentication as a startup task
    @mcp.lifecycle.on_startup
    async def startup():
        await server.authenticate()
        logger.info("GCP observability server started")

    # Register cleanup on shutdown
    @mcp.lifecycle.on_shutdown
    async def shutdown():
        await server.close()
        logger.info("GCP observability server stopped")

    # Register tools
    server.register_tools(mcp)

    return mcp
