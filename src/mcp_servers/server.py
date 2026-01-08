"""Standalone MCP server runner.

This module provides a configurable MCP server that can serve observability
tools for one or more cloud projects. It's designed to be run as a subprocess
by the MCP client.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.config_manager import ConfigManager
from src.core.exceptions import ConfigurationError
from src.core.logger import get_logger, setup_logging
from src.models.config import CloudProvider
from src.mcp_servers.gcp_observability import create_gcp_mcp_server


logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="MCP Observability Server",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file"
    )

    parser.add_argument(
        "--project",
        type=str,
        required=True,
        help="Project name to serve (from configuration)"
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level"
    )

    parser.add_argument(
        "--log-format",
        type=str,
        default="text",
        choices=["json", "text"],
        help="Log format"
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point for MCP server.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    args = parse_args()

    # Setup logging (stderr to avoid interfering with stdio MCP transport)
    setup_logging(
        level=args.log_level,
        log_format=args.log_format
    )

    try:
        # Load configuration
        logger.info(f"Loading configuration for project: {args.project}")

        if args.config:
            config_manager = ConfigManager(args.config)
        else:
            # Try to find config in default locations
            from src.core.config_manager import load_config
            config_manager = load_config()

        # Get project configuration
        project_config = config_manager.config.get_project(args.project)
        if not project_config:
            logger.error(f"Project '{args.project}' not found in configuration")
            return 1

        if not project_config.enabled:
            logger.error(f"Project '{args.project}' is disabled")
            return 1

        # Create appropriate MCP server based on provider
        logger.info(
            f"Creating MCP server for {project_config.provider} project",
            extra={
                "project": args.project,
                "provider": project_config.provider.value
            }
        )

        if project_config.provider == CloudProvider.GCP:
            mcp_server = create_gcp_mcp_server(project_config)
        elif project_config.provider == CloudProvider.AWS:
            logger.error("AWS support not yet implemented")
            return 1
        elif project_config.provider == CloudProvider.AZURE:
            logger.error("Azure support not yet implemented")
            return 1
        else:
            logger.error(f"Unsupported provider: {project_config.provider}")
            return 1

        # Run the MCP server
        logger.info("Starting MCP server (stdio transport)")
        mcp_server.run(transport='stdio')

        return 0

    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}", exc_info=True)
        return 1

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
