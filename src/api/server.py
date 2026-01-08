"""Production-grade RCA webhook server.

This module provides the main HTTP server for receiving alerts and
orchestrating root cause analysis across multiple projects.
"""

import asyncio
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from quart import Quart, request, jsonify, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

from src.core.config_manager import ConfigManager, load_config
from src.core.exceptions import RCAException
from src.core.logger import (
    get_logger,
    setup_logging,
    set_correlation_id,
    set_project_context,
    clear_context
)
from src.mcp_client.client import MCPClient, RCARequest
from src.utils.prompt_manager import PromptManager

logger = get_logger(__name__)


# Prometheus metrics
ALERTS_RECEIVED = Counter(
    "rca_alerts_received_total",
    "Total alerts received",
    ["project", "status"]
)

ALERTS_PROCESSING = Gauge(
    "rca_alerts_processing",
    "Current alerts being processed",
    ["project"]
)

ALERT_PROCESSING_DURATION = Histogram(
    "rca_alert_processing_duration_seconds",
    "Alert processing duration",
    ["project", "status"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]
)

TOOL_CALLS = Histogram(
    "rca_tool_calls_per_alert",
    "Number of MCP tool calls per alert",
    ["project"],
    buckets=[0, 1, 2, 5, 10, 15, 20, 30]
)

API_REQUESTS = Counter(
    "rca_api_requests_total",
    "Total API requests",
    ["endpoint", "method", "status"]
)


class RCAServer:
    """Root Cause Analysis webhook server.

    Handles incoming alerts, routes them to appropriate projects,
    and orchestrates concurrent RCA execution.
    """

    def __init__(
        self,
        config_manager: ConfigManager,
        mcp_client: MCPClient,
        prompt_manager: PromptManager
    ):
        """Initialize RCA server.

        Args:
            config_manager: Configuration manager
            mcp_client: MCP client for analysis
            prompt_manager: Prompt template manager
        """
        self.config_manager = config_manager
        self.config = config_manager.config
        self.mcp_client = mcp_client
        self.prompt_manager = prompt_manager

        # Semaphore for concurrent alert processing
        self.processing_semaphore = asyncio.Semaphore(
            self.config.alerts.max_concurrent_alerts
        )

        logger.info(
            "RCA server initialized",
            extra={
                "projects": len(self.config.projects),
                "max_concurrent": self.config.alerts.max_concurrent_alerts
            }
        )

    async def process_alert(
        self,
        alert_data: Dict[str, Any],
        project_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process an incoming alert.

        Args:
            alert_data: Alert payload
            project_name: Optional project name (can be inferred from alert)

        Returns:
            Processing result dictionary

        Raises:
            RCAException: If processing fails
        """
        correlation_id = str(uuid.uuid4())
        set_correlation_id(correlation_id)

        try:
            # Extract project name if not provided
            if not project_name:
                project_name = self._infer_project(alert_data)

            set_project_context(project_name)

            logger.info(
                f"Processing alert for project {project_name}",
                extra={"correlation_id": correlation_id}
            )

            # Get project configuration
            project_config = self.config.get_project(project_name)
            if not project_config:
                raise RCAException(
                    f"Project not found: {project_name}",
                    {"available_projects": [p.name for p in self.config.projects]}
                )

            if not project_config.enabled:
                raise RCAException(
                    f"Project {project_name} is disabled",
                    {"project": project_name}
                )

            # Update metrics
            ALERTS_RECEIVED.labels(project=project_name, status="received").inc()
            ALERTS_PROCESSING.labels(project=project_name).inc()

            try:
                # Acquire semaphore for concurrent processing
                async with self.processing_semaphore:
                    # Extract alert details
                    incident = alert_data.get("incident", {})
                    alert_summary = incident.get("summary", "No summary provided")
                    alert_documentation = incident.get("documentation", {}).get("content", "")

                    # Build prompt
                    prompt = self.prompt_manager.build_prompt(
                        project_config=project_config,
                        alert_summary=alert_summary,
                        alert_documentation=alert_documentation,
                        incident_data=alert_data
                    )

                    # Create RCA request
                    rca_request = RCARequest(
                        project_name=project_name,
                        alert_summary=alert_summary,
                        alert_documentation=alert_documentation,
                        incident_data=alert_data,
                        correlation_id=correlation_id
                    )

                    # Perform analysis
                    with ALERT_PROCESSING_DURATION.labels(
                        project=project_name,
                        status="success"
                    ).time():
                        response = await self.mcp_client.analyze(rca_request)

                    # Record metrics
                    TOOL_CALLS.labels(project=project_name).observe(
                        response.tool_calls_count
                    )

                    if response.status == "success":
                        ALERTS_RECEIVED.labels(
                            project=project_name,
                            status="success"
                        ).inc()

                        logger.info(
                            "Alert processed successfully",
                            extra={
                                "correlation_id": correlation_id,
                                "tool_calls": response.tool_calls_count,
                                "execution_time": response.execution_time_seconds
                            }
                        )

                        return {
                            "status": "success",
                            "correlation_id": correlation_id,
                            "analysis": response.analysis,
                            "tool_calls": response.tool_calls_count,
                            "execution_time_seconds": response.execution_time_seconds
                        }
                    else:
                        raise RCAException(
                            "Analysis failed",
                            {"error": response.error}
                        )

            finally:
                ALERTS_PROCESSING.labels(project=project_name).dec()

        except RCAException:
            raise
        except Exception as e:
            ALERTS_RECEIVED.labels(
                project=project_name or "unknown",
                status="error"
            ).inc()
            raise RCAException(
                f"Failed to process alert",
                {"error": str(e), "correlation_id": correlation_id}
            ) from e
        finally:
            clear_context()

    def _infer_project(self, alert_data: Dict[str, Any]) -> str:
        """Infer project name from alert data.

        Args:
            alert_data: Alert payload

        Returns:
            Project name

        Raises:
            RCAException: If project cannot be inferred
        """
        # Try to extract from incident metadata
        incident = alert_data.get("incident", {})
        metadata = incident.get("metadata", {})

        # Check for project label/tag
        if "project" in metadata:
            return metadata["project"]

        if "project_id" in metadata:
            # Try to find project by project_id
            project_id = metadata["project_id"]
            for project in self.config.projects:
                if (
                    project.gcp and
                    project.gcp.project_id == project_id
                ):
                    return project.name

        # If only one project configured, use it
        enabled_projects = self.config.get_enabled_projects()
        if len(enabled_projects) == 1:
            return enabled_projects[0].name

        raise RCAException(
            "Cannot infer project from alert data",
            {
                "message": "Provide 'project' in request or alert metadata",
                "available_projects": [p.name for p in enabled_projects]
            }
        )


def create_app(
    config_path: Optional[Path] = None,
    config_manager: Optional[ConfigManager] = None
) -> tuple[Quart, RCAServer]:
    """Create and configure the Quart application.

    Args:
        config_path: Optional path to configuration file
        config_manager: Optional pre-initialized config manager

    Returns:
        Tuple of (Quart app, RCAServer instance)
    """
    # Load configuration
    if config_manager is None:
        if config_path:
            config_manager = ConfigManager(config_path)
        else:
            config_manager = load_config()

    config = config_manager.config

    # Setup logging
    setup_logging(
        level=config.observability.log_level,
        log_format=config.observability.log_format
    )

    logger.info("Starting RCA platform")

    # Initialize components
    mcp_client = MCPClient(config.anthropic)
    prompt_manager = PromptManager(config.prompt_templates_dir)

    # Register MCP servers for each enabled project
    for project in config.get_enabled_projects():
        server_script = Path(__file__).parent.parent / "mcp_servers" / "server.py"

        # The server.py will be invoked with --project argument
        mcp_client.register_project(project, server_script)

        logger.info(
            f"Registered project: {project.name}",
            extra={
                "provider": project.provider.value,
                "display_name": project.display_name
            }
        )

    # Create RCA server
    rca_server = RCAServer(config_manager, mcp_client, prompt_manager)

    # Create Quart app
    app = Quart(__name__)
    app.config["rca_server"] = rca_server
    app.config["platform_config"] = config

    # Health check endpoint
    @app.route("/health", methods=["GET"])
    async def health():
        """Health check endpoint."""
        API_REQUESTS.labels(endpoint="/health", method="GET", status="200").inc()

        return jsonify({
            "status": "healthy",
            "version": config.version,
            "projects": len(config.projects),
            "enabled_projects": len(config.get_enabled_projects())
        }), 200

    # Metrics endpoint
    @app.route("/metrics", methods=["GET"])
    async def metrics():
        """Prometheus metrics endpoint."""
        API_REQUESTS.labels(endpoint="/metrics", method="GET", status="200").inc()

        metrics_output = generate_latest()
        return Response(metrics_output, mimetype=CONTENT_TYPE_LATEST)

    # Alert webhook endpoint
    @app.route(config.alerts.path, methods=["POST"])
    async def alert_webhook():
        """Alert webhook endpoint."""
        try:
            alert_data = await request.get_json()

            # Optional project override from query params
            project_name = request.args.get("project")

            # Authenticate if token configured
            if config.alerts.auth_token:
                auth_header = request.headers.get("Authorization", "")
                expected = f"Bearer {config.alerts.auth_token}"
                if auth_header != expected:
                    API_REQUESTS.labels(
                        endpoint=config.alerts.path,
                        method="POST",
                        status="401"
                    ).inc()
                    return jsonify({"error": "Unauthorized"}), 401

            # Process alert asynchronously (don't block webhook response)
            asyncio.create_task(
                rca_server.process_alert(alert_data, project_name)
            )

            API_REQUESTS.labels(
                endpoint=config.alerts.path,
                method="POST",
                status="202"
            ).inc()

            return jsonify({
                "status": "accepted",
                "message": "Alert processing started"
            }), 202

        except Exception as e:
            logger.error(
                "Alert webhook error",
                extra={"error": str(e)},
                exc_info=True
            )

            API_REQUESTS.labels(
                endpoint=config.alerts.path,
                method="POST",
                status="500"
            ).inc()

            return jsonify({
                "status": "error",
                "message": str(e)
            }), 500

    # Project list endpoint
    @app.route("/projects", methods=["GET"])
    async def list_projects():
        """List configured projects."""
        API_REQUESTS.labels(endpoint="/projects", method="GET", status="200").inc()

        projects = [
            {
                "name": p.name,
                "display_name": p.display_name,
                "provider": p.provider.value,
                "enabled": p.enabled,
                "description": p.description
            }
            for p in config.projects
        ]

        return jsonify({"projects": projects}), 200

    logger.info(
        f"Application created successfully",
        extra={
            "alert_endpoint": config.alerts.path,
            "metrics_port": config.observability.metrics_port
        }
    )

    return app, rca_server


def main():
    """Main entry point for running the server."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="RCA Platform Server")
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file"
    )
    parser.add_argument(
        "--host",
        type=str,
        help="Host to bind to (overrides config)"
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Port to bind to (overrides config)"
    )

    args = parser.parse_args()

    try:
        app, rca_server = create_app(args.config)
        config = app.config["platform_config"]

        host = args.host or config.alerts.host
        port = args.port or config.alerts.port

        logger.info(f"Starting server on {host}:{port}")

        # Run with Quart's built-in server (use Hypercorn for production)
        app.run(host=host, port=port, debug=False)

    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
