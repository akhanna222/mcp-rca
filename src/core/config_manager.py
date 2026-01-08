"""Configuration management for the RCA platform.

This module provides centralized configuration loading, validation,
and management with support for multiple formats and environments.
"""

import json
import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from src.models.config import PlatformConfig
from src.core.exceptions import ConfigurationError
from src.core.logger import get_logger

logger = get_logger(__name__)


class ConfigManager:
    """Manager for platform configuration.

    Handles loading, validating, and accessing configuration from various sources
    with support for environment variables and multiple file formats.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration manager.

        Args:
            config_path: Path to configuration file (JSON or YAML)

        Raises:
            ConfigurationError: If configuration is invalid
        """
        self._config: Optional[PlatformConfig] = None
        self._config_path = config_path

        if config_path:
            self.load_from_file(config_path)

    def load_from_file(self, config_path: Path) -> PlatformConfig:
        """Load configuration from a file.

        Supports JSON and YAML formats. File type is determined by extension.

        Args:
            config_path: Path to configuration file

        Returns:
            Loaded and validated platform configuration

        Raises:
            ConfigurationError: If file doesn't exist, is invalid, or validation fails
        """
        if not config_path.exists():
            raise ConfigurationError(
                f"Configuration file not found: {config_path}",
                {"path": str(config_path)}
            )

        logger.info(f"Loading configuration from {config_path}")

        try:
            # Read file content
            content = config_path.read_text(encoding="utf-8")

            # Parse based on file extension
            suffix = config_path.suffix.lower()
            if suffix in [".yaml", ".yml"]:
                data = yaml.safe_load(content)
            elif suffix == ".json":
                data = json.loads(content)
            else:
                raise ConfigurationError(
                    f"Unsupported configuration format: {suffix}",
                    {"supported": [".yaml", ".yml", ".json"]}
                )

            # Validate and create config
            self._config = PlatformConfig(**data)
            self._config_path = config_path

            logger.info(
                "Configuration loaded successfully",
                extra={
                    "projects_count": len(self._config.projects),
                    "enabled_projects": len(self._config.get_enabled_projects())
                }
            )

            return self._config

        except yaml.YAMLError as e:
            raise ConfigurationError(
                f"Invalid YAML syntax in configuration file",
                {"path": str(config_path), "error": str(e)}
            ) from e

        except json.JSONDecodeError as e:
            raise ConfigurationError(
                f"Invalid JSON syntax in configuration file",
                {"path": str(config_path), "error": str(e)}
            ) from e

        except ValidationError as e:
            raise ConfigurationError(
                f"Configuration validation failed",
                {
                    "path": str(config_path),
                    "errors": e.errors()
                }
            ) from e

    def load_from_dict(self, config_dict: dict) -> PlatformConfig:
        """Load configuration from a dictionary.

        Args:
            config_dict: Configuration as a dictionary

        Returns:
            Loaded and validated platform configuration

        Raises:
            ConfigurationError: If validation fails
        """
        try:
            self._config = PlatformConfig(**config_dict)
            logger.info("Configuration loaded from dictionary")
            return self._config

        except ValidationError as e:
            raise ConfigurationError(
                "Configuration validation failed",
                {"errors": e.errors()}
            ) from e

    def load_from_env(self) -> PlatformConfig:
        """Load configuration from environment variables.

        Uses Pydantic's settings management to load from environment.
        Environment variables should be prefixed with the nested path,
        e.g., ANTHROPIC__API_KEY for anthropic.api_key

        Returns:
            Loaded and validated platform configuration

        Raises:
            ConfigurationError: If validation fails
        """
        try:
            self._config = PlatformConfig()
            logger.info("Configuration loaded from environment variables")
            return self._config

        except ValidationError as e:
            raise ConfigurationError(
                "Configuration validation failed",
                {"errors": e.errors()}
            ) from e

    @property
    def config(self) -> PlatformConfig:
        """Get current platform configuration.

        Returns:
            Current platform configuration

        Raises:
            ConfigurationError: If no configuration is loaded
        """
        if self._config is None:
            raise ConfigurationError("No configuration loaded")
        return self._config

    def reload(self) -> PlatformConfig:
        """Reload configuration from the original source.

        Returns:
            Reloaded configuration

        Raises:
            ConfigurationError: If no configuration path is set
        """
        if self._config_path is None:
            raise ConfigurationError("Cannot reload: no configuration path set")

        logger.info("Reloading configuration")
        return self.load_from_file(self._config_path)

    def validate(self) -> bool:
        """Validate current configuration.

        Returns:
            True if configuration is valid

        Raises:
            ConfigurationError: If configuration is invalid
        """
        if self._config is None:
            raise ConfigurationError("No configuration loaded")

        # Re-validate the model
        try:
            PlatformConfig(**self._config.model_dump())
            logger.info("Configuration validation successful")
            return True
        except ValidationError as e:
            raise ConfigurationError(
                "Configuration validation failed",
                {"errors": e.errors()}
            ) from e

    def save_to_file(self, output_path: Path, format: str = "yaml") -> None:
        """Save current configuration to a file.

        Args:
            output_path: Path where to save the configuration
            format: Output format ('yaml' or 'json')

        Raises:
            ConfigurationError: If no configuration is loaded or format is invalid
        """
        if self._config is None:
            raise ConfigurationError("No configuration loaded")

        logger.info(f"Saving configuration to {output_path}")

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert config to dict
        config_dict = self._config.model_dump(mode='json', exclude_none=True)

        try:
            if format == "yaml":
                with output_path.open("w", encoding="utf-8") as f:
                    yaml.safe_dump(
                        config_dict,
                        f,
                        default_flow_style=False,
                        sort_keys=False,
                        indent=2
                    )
            elif format == "json":
                with output_path.open("w", encoding="utf-8") as f:
                    json.dump(config_dict, f, indent=2)
            else:
                raise ConfigurationError(
                    f"Unsupported output format: {format}",
                    {"supported": ["yaml", "json"]}
                )

            logger.info(f"Configuration saved successfully to {output_path}")

        except Exception as e:
            raise ConfigurationError(
                f"Failed to save configuration",
                {"path": str(output_path), "error": str(e)}
            ) from e

    def get_anthropic_api_key(self) -> str:
        """Get Anthropic API key from config or environment.

        Returns:
            Anthropic API key

        Raises:
            ConfigurationError: If API key is not configured
        """
        if self._config is None:
            raise ConfigurationError("No configuration loaded")

        # Check config first
        if self._config.anthropic.api_key:
            return self._config.anthropic.api_key

        # Check environment variable
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            return api_key

        raise ConfigurationError(
            "Anthropic API key not configured",
            {
                "message": "Set ANTHROPIC_API_KEY environment variable or "
                          "configure anthropic.api_key in config file"
            }
        )


def load_config(
    config_path: Optional[Path] = None,
    env_var: str = "RCA_CONFIG_PATH"
) -> ConfigManager:
    """Load configuration from file or environment.

    Args:
        config_path: Optional path to configuration file
        env_var: Environment variable name for config path

    Returns:
        Initialized ConfigManager

    Raises:
        ConfigurationError: If configuration cannot be loaded
    """
    # Try provided path first
    if config_path:
        return ConfigManager(config_path)

    # Try environment variable
    env_path = os.getenv(env_var)
    if env_path:
        return ConfigManager(Path(env_path))

    # Try default locations
    default_paths = [
        Path("config/platform.yaml"),
        Path("config/platform.yml"),
        Path("config/platform.json"),
        Path("platform.yaml"),
        Path("platform.yml"),
        Path("platform.json"),
    ]

    for path in default_paths:
        if path.exists():
            return ConfigManager(path)

    raise ConfigurationError(
        "No configuration file found",
        {
            "message": f"Provide config path via {env_var} environment variable "
                      f"or create one of: {[str(p) for p in default_paths]}"
        }
    )
