#!/usr/bin/env python3
"""Command-line interface for MCP-RCA platform management.

This CLI provides tools for configuration validation, health checks,
and platform management operations.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from src.core.config_manager import ConfigManager, load_config
from src.core.exceptions import ConfigurationError, RCAException
from src.core.logger import get_logger, setup_logging


logger = get_logger(__name__)


def setup_args() -> argparse.ArgumentParser:
    """Setup command-line argument parser.

    Returns:
        Configured argument parser
    """
    parser = argparse.ArgumentParser(
        description="MCP-RCA Platform Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate configuration
  %(prog)s validate --config config/platform.yaml

  # Check health of all projects
  %(prog)s health --config config/platform.yaml

  # List configured projects
  %(prog)s projects --config config/platform.yaml

  # Generate example configuration
  %(prog)s generate-config --output config/my-config.yaml

  # Test MCP server connection
  %(prog)s test-mcp --config config/platform.yaml --project my-project
        """
    )

    parser.add_argument(
        "--config",
        type=Path,
        help="Path to platform configuration file"
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
        help="Log output format"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate configuration file"
    )
    validate_parser.add_argument(
        "--strict",
        action="store_true",
        help="Enable strict validation mode"
    )

    # Health command
    subparsers.add_parser(
        "health",
        help="Check health of all configured projects"
    )

    # Projects command
    projects_parser = subparsers.add_parser(
        "projects",
        help="List configured projects"
    )
    projects_parser.add_argument(
        "--enabled-only",
        action="store_true",
        help="Show only enabled projects"
    )
    projects_parser.add_argument(
        "--format",
        type=str,
        default="table",
        choices=["table", "json", "yaml"],
        help="Output format"
    )

    # Generate config command
    gen_config_parser = subparsers.add_parser(
        "generate-config",
        help="Generate example configuration file"
    )
    gen_config_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output file path"
    )
    gen_config_parser.add_argument(
        "--template",
        type=str,
        default="single-gcp",
        choices=["single-gcp", "multi-project", "minimal"],
        help="Configuration template to use"
    )

    # Test MCP command
    test_mcp_parser = subparsers.add_parser(
        "test-mcp",
        help="Test MCP server connection for a project"
    )
    test_mcp_parser.add_argument(
        "--project",
        type=str,
        required=True,
        help="Project name to test"
    )

    # Info command
    subparsers.add_parser(
        "info",
        help="Display platform information and statistics"
    )

    return parser


def cmd_validate(config_manager: ConfigManager, args: argparse.Namespace) -> int:
    """Validate configuration.

    Args:
        config_manager: Configuration manager instance
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        config = config_manager.config
        logger.info("Configuration validation successful")

        print("✓ Configuration is valid")
        print(f"\nProjects configured: {len(config.projects)}")
        print(f"Enabled projects: {len(config.get_enabled_projects())}")

        if args.strict:
            # Perform additional strict validation
            logger.info("Running strict validation checks")

            # Check for required API keys
            if not config_manager.get_anthropic_api_key():
                print("⚠ Warning: ANTHROPIC_API_KEY not configured")
                return 1

            # Validate each project can be initialized
            for project in config.get_enabled_projects():
                print(f"\nValidating project: {project.name}")

                if project.provider.value == "gcp":
                    if not project.gcp:
                        print(f"  ✗ Missing GCP configuration")
                        return 1

                    print(f"  ✓ Provider: {project.provider.value}")
                    print(f"  ✓ Monitoring queries: {len(project.gcp.monitoring.queries)}")
                    print(f"  ✓ Log filters: {len(project.gcp.logging.filters)}")

        return 0

    except ConfigurationError as e:
        logger.error(f"Configuration validation failed: {e}")
        print(f"✗ Configuration validation failed:")
        print(f"  {e.message}")
        if e.details:
            print(f"  Details: {json.dumps(e.details, indent=2)}")
        return 1


async def cmd_health(config_manager: ConfigManager, args: argparse.Namespace) -> int:
    """Check health of all projects.

    Args:
        config_manager: Configuration manager instance
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    config = config_manager.config
    enabled_projects = config.get_enabled_projects()

    print(f"Checking health of {len(enabled_projects)} project(s)...\n")

    all_healthy = True

    for project in enabled_projects:
        print(f"Project: {project.name} ({project.provider.value})")

        try:
            if project.provider.value == "gcp":
                # Import here to avoid circular dependencies
                from src.mcp_servers.gcp_observability import GCPObservabilityServer

                server = GCPObservabilityServer(project)
                await server.authenticate()

                is_healthy = await server.health_check()

                if is_healthy:
                    print(f"  ✓ Healthy")
                else:
                    print(f"  ✗ Unhealthy")
                    all_healthy = False

                await server.close()

            else:
                print(f"  ⚠ Health check not implemented for {project.provider.value}")

        except Exception as e:
            print(f"  ✗ Error: {str(e)}")
            all_healthy = False

        print()

    return 0 if all_healthy else 1


def cmd_projects(config_manager: ConfigManager, args: argparse.Namespace) -> int:
    """List configured projects.

    Args:
        config_manager: Configuration manager instance
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    config = config_manager.config

    projects = (
        config.get_enabled_projects()
        if args.enabled_only
        else config.projects
    )

    if args.format == "json":
        data = [
            {
                "name": p.name,
                "display_name": p.display_name,
                "provider": p.provider.value,
                "enabled": p.enabled,
                "description": p.description
            }
            for p in projects
        ]
        print(json.dumps({"projects": data}, indent=2))

    elif args.format == "yaml":
        import yaml
        data = [
            {
                "name": p.name,
                "display_name": p.display_name,
                "provider": p.provider.value,
                "enabled": p.enabled,
                "description": p.description
            }
            for p in projects
        ]
        print(yaml.dump({"projects": data}, default_flow_style=False))

    else:  # table format
        print(f"{'Name':<20} {'Display Name':<30} {'Provider':<10} {'Status':<10}")
        print("-" * 72)

        for project in projects:
            status = "Enabled" if project.enabled else "Disabled"
            print(
                f"{project.name:<20} "
                f"{project.display_name:<30} "
                f"{project.provider.value:<10} "
                f"{status:<10}"
            )

        print(f"\nTotal: {len(projects)} project(s)")

    return 0


def cmd_generate_config(args: argparse.Namespace) -> int:
    """Generate example configuration file.

    Args:
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    templates_dir = Path(__file__).parent.parent / "examples"

    template_map = {
        "single-gcp": "config_single_project_gcp.yaml",
        "multi-project": "config_multi_project.yaml",
        "minimal": "config_single_project_gcp.yaml",
    }

    template_file = templates_dir / template_map[args.template]

    if not template_file.exists():
        print(f"✗ Template file not found: {template_file}")
        return 1

    try:
        # Copy template to output location
        args.output.parent.mkdir(parents=True, exist_ok=True)

        import shutil
        shutil.copy(template_file, args.output)

        print(f"✓ Configuration generated: {args.output}")
        print(f"\nNext steps:")
        print(f"1. Edit {args.output} and update:")
        print(f"   - Project IDs and credentials")
        print(f"   - Monitoring queries")
        print(f"   - Log filters")
        print(f"2. Set environment variable: export ANTHROPIC_API_KEY=your-key")
        print(f"3. Validate: {sys.argv[0]} validate --config {args.output}")
        print(f"4. Run platform: python src/api/server.py --config {args.output}")

        return 0

    except Exception as e:
        print(f"✗ Failed to generate configuration: {e}")
        return 1


async def cmd_test_mcp(config_manager: ConfigManager, args: argparse.Namespace) -> int:
    """Test MCP server connection.

    Args:
        config_manager: Configuration manager instance
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    config = config_manager.config
    project = config.get_project(args.project)

    if not project:
        print(f"✗ Project not found: {args.project}")
        return 1

    if not project.enabled:
        print(f"✗ Project is disabled: {args.project}")
        return 1

    print(f"Testing MCP server for project: {project.name}")
    print(f"Provider: {project.provider.value}\n")

    try:
        if project.provider.value == "gcp":
            from src.mcp_servers.gcp_observability import GCPObservabilityServer

            server = GCPObservabilityServer(project)

            # Test authentication
            print("1. Testing authentication...")
            await server.authenticate()
            print("   ✓ Authentication successful\n")

            # Test health check
            print("2. Testing health check...")
            is_healthy = await server.health_check()
            if is_healthy:
                print("   ✓ Health check passed\n")
            else:
                print("   ✗ Health check failed\n")
                return 1

            # Test metrics query
            if project.gcp.monitoring.enabled and project.gcp.monitoring.queries:
                print("3. Testing metrics query...")
                test_query = project.gcp.monitoring.queries[0]
                results = await server.query_metrics(
                    [(test_query.query, test_query.purpose)]
                )
                print(f"   ✓ Query executed: {test_query.name}")
                print(f"   Results: {len(results)} metric(s) returned\n")

            # Test logs query
            if project.gcp.logging.enabled and project.gcp.logging.filters:
                print("4. Testing logs query...")
                test_filter = project.gcp.logging.filters[0]
                results = await server.query_logs(
                    test_filter.filter_query,
                    time_range_minutes=5.0,
                    max_entries=10
                )
                print(f"   ✓ Query executed: {test_filter.name}")
                print(f"   Results: {len(results)} log entries returned\n")

            await server.close()

            print("✓ All MCP server tests passed")
            return 0

        else:
            print(f"✗ Testing not implemented for {project.provider.value}")
            return 1

    except Exception as e:
        print(f"✗ MCP server test failed: {e}")
        logger.error("MCP test failed", exc_info=True)
        return 1


def cmd_info(config_manager: ConfigManager, args: argparse.Namespace) -> int:
    """Display platform information.

    Args:
        config_manager: Configuration manager instance
        args: Command arguments

    Returns:
        Exit code (0 for success)
    """
    config = config_manager.config

    print("MCP-RCA Platform Information")
    print("=" * 50)
    print(f"\nVersion: {config.version}")
    print(f"\nProjects:")
    print(f"  Total: {len(config.projects)}")
    print(f"  Enabled: {len(config.get_enabled_projects())}")
    print(f"  Disabled: {len(config.projects) - len(config.get_enabled_projects())}")

    print(f"\nProviders:")
    providers = {}
    for project in config.projects:
        provider = project.provider.value
        providers[provider] = providers.get(provider, 0) + 1

    for provider, count in sorted(providers.items()):
        print(f"  {provider}: {count}")

    print(f"\nAnthropicConfiguration:")
    print(f"  Model: {config.anthropic.model}")
    print(f"  Max tokens: {config.anthropic.max_tokens}")
    print(f"  Timeout: {config.anthropic.timeout_seconds}s")

    print(f"\nAlert Configuration:")
    print(f"  Host: {config.alerts.host}")
    print(f"  Port: {config.alerts.port}")
    print(f"  Path: {config.alerts.path}")
    print(f"  Max concurrent: {config.alerts.max_concurrent_alerts}")
    print(f"  Auth enabled: {'Yes' if config.alerts.auth_token else 'No'}")

    print(f"\nObservability:")
    print(f"  Log level: {config.observability.log_level}")
    print(f"  Log format: {config.observability.log_format}")
    print(f"  Metrics port: {config.observability.metrics_port}")

    return 0


def main() -> int:
    """Main CLI entry point.

    Returns:
        Exit code
    """
    parser = setup_args()
    args = parser.parse_args()

    # Setup logging
    setup_logging(
        level=args.log_level,
        log_format=args.log_format
    )

    # Special handling for generate-config (doesn't need config file)
    if args.command == "generate-config":
        return cmd_generate_config(args)

    # All other commands require configuration
    if not args.command:
        parser.print_help()
        return 1

    try:
        # Load configuration
        if args.config:
            config_manager = ConfigManager(args.config)
        else:
            config_manager = load_config()

        # Execute command
        if args.command == "validate":
            return cmd_validate(config_manager, args)

        elif args.command == "health":
            return asyncio.run(cmd_health(config_manager, args))

        elif args.command == "projects":
            return cmd_projects(config_manager, args)

        elif args.command == "test-mcp":
            return asyncio.run(cmd_test_mcp(config_manager, args))

        elif args.command == "info":
            return cmd_info(config_manager, args)

        else:
            parser.print_help()
            return 1

    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        print(f"✗ Configuration error: {e.message}")
        return 1

    except RCAException as e:
        logger.error(f"RCA error: {e}")
        print(f"✗ Error: {e.message}")
        return 1

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"✗ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
