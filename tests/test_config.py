"""Tests for configuration management.

This module tests configuration loading, validation, and management
to ensure all configuration scenarios work correctly.
"""

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from src.core.config_manager import ConfigManager, load_config
from src.core.exceptions import ConfigurationError
from src.models.config import (
    AlertConfig,
    AnthropicConfig,
    CloudProvider,
    GCPAuth,
    GCPConfig,
    LogFilter,
    LoggingConfig,
    MonitoringConfig,
    MonitoringQuery,
    ObservabilityConfig,
    PlatformConfig,
    ProjectConfig,
)


class TestConfigModels:
    """Test configuration Pydantic models."""

    def test_minimal_platform_config(self):
        """Test minimal valid platform configuration."""
        config = PlatformConfig(
            projects=[
                ProjectConfig(
                    name="test-project",
                    display_name="Test Project",
                    provider=CloudProvider.GCP,
                    gcp=GCPConfig(
                        project_id="test-gcp-project"
                    )
                )
            ]
        )

        assert len(config.projects) == 1
        assert config.projects[0].name == "test-project"
        assert config.anthropic.model == "claude-3-7-sonnet-20250219"

    def test_project_config_validation(self):
        """Test project configuration validation."""
        # Missing GCP config for GCP provider
        with pytest.raises(ValueError, match="Provider 'gcp' requires corresponding config"):
            ProjectConfig(
                name="test",
                display_name="Test",
                provider=CloudProvider.GCP
            )

    def test_unique_project_names(self):
        """Test that duplicate project names are rejected."""
        with pytest.raises(ValueError, match="Project names must be unique"):
            PlatformConfig(
                projects=[
                    ProjectConfig(
                        name="duplicate",
                        display_name="First",
                        provider=CloudProvider.GCP,
                        gcp=GCPConfig(project_id="project-1")
                    ),
                    ProjectConfig(
                        name="duplicate",
                        display_name="Second",
                        provider=CloudProvider.GCP,
                        gcp=GCPConfig(project_id="project-2")
                    )
                ]
            )

    def test_monitoring_query_model(self):
        """Test monitoring query configuration."""
        query = MonitoringQuery(
            name="CPU Usage",
            query="avg(cpu_usage)",
            purpose="Monitor CPU utilization"
        )

        assert query.enabled is True
        assert query.name == "CPU Usage"

    def test_log_filter_model(self):
        """Test log filter configuration."""
        filter_obj = LogFilter(
            name="Errors",
            filter_query="severity>=ERROR",
            purpose="Application errors"
        )

        assert filter_obj.enabled is True
        assert filter_obj.filter_query == "severity>=ERROR"


class TestConfigManager:
    """Test configuration manager functionality."""

    def test_load_from_dict(self):
        """Test loading configuration from dictionary."""
        config_dict = {
            "projects": [
                {
                    "name": "test",
                    "display_name": "Test Project",
                    "provider": "gcp",
                    "gcp": {
                        "project_id": "test-project-id"
                    }
                }
            ]
        }

        manager = ConfigManager()
        config = manager.load_from_dict(config_dict)

        assert len(config.projects) == 1
        assert config.projects[0].name == "test"

    def test_load_from_yaml_file(self):
        """Test loading configuration from YAML file."""
        config_data = {
            "version": "1.0.0",
            "projects": [
                {
                    "name": "yaml-test",
                    "display_name": "YAML Test",
                    "provider": "gcp",
                    "gcp": {
                        "project_id": "yaml-project"
                    }
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            temp_path = Path(f.name)

        try:
            manager = ConfigManager(temp_path)
            config = manager.config

            assert config.version == "1.0.0"
            assert len(config.projects) == 1
            assert config.projects[0].name == "yaml-test"

        finally:
            temp_path.unlink()

    def test_load_from_json_file(self):
        """Test loading configuration from JSON file."""
        config_data = {
            "version": "1.0.0",
            "projects": [
                {
                    "name": "json-test",
                    "display_name": "JSON Test",
                    "provider": "gcp",
                    "gcp": {
                        "project_id": "json-project"
                    }
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = Path(f.name)

        try:
            manager = ConfigManager(temp_path)
            config = manager.config

            assert config.version == "1.0.0"
            assert len(config.projects) == 1

        finally:
            temp_path.unlink()

    def test_invalid_yaml_syntax(self):
        """Test handling of invalid YAML syntax."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: syntax:\n  - broken")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ConfigurationError, match="Invalid YAML syntax"):
                ConfigManager(temp_path)

        finally:
            temp_path.unlink()

    def test_invalid_json_syntax(self):
        """Test handling of invalid JSON syntax."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{invalid json")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ConfigurationError, match="Invalid JSON syntax"):
                ConfigManager(temp_path)

        finally:
            temp_path.unlink()

    def test_get_project(self):
        """Test retrieving project by name."""
        config_dict = {
            "projects": [
                {
                    "name": "project-1",
                    "display_name": "Project 1",
                    "provider": "gcp",
                    "gcp": {"project_id": "proj-1"}
                },
                {
                    "name": "project-2",
                    "display_name": "Project 2",
                    "provider": "gcp",
                    "gcp": {"project_id": "proj-2"}
                }
            ]
        }

        manager = ConfigManager()
        config = manager.load_from_dict(config_dict)

        project = config.get_project("project-1")
        assert project is not None
        assert project.name == "project-1"

        project = config.get_project("non-existent")
        assert project is None

    def test_get_enabled_projects(self):
        """Test filtering enabled projects."""
        config_dict = {
            "projects": [
                {
                    "name": "enabled",
                    "display_name": "Enabled",
                    "provider": "gcp",
                    "enabled": True,
                    "gcp": {"project_id": "enabled"}
                },
                {
                    "name": "disabled",
                    "display_name": "Disabled",
                    "provider": "gcp",
                    "enabled": False,
                    "gcp": {"project_id": "disabled"}
                }
            ]
        }

        manager = ConfigManager()
        config = manager.load_from_dict(config_dict)

        enabled = config.get_enabled_projects()
        assert len(enabled) == 1
        assert enabled[0].name == "enabled"

    def test_save_to_yaml(self):
        """Test saving configuration to YAML file."""
        config_dict = {
            "version": "1.0.0",
            "projects": [
                {
                    "name": "save-test",
                    "display_name": "Save Test",
                    "provider": "gcp",
                    "gcp": {"project_id": "save-project"}
                }
            ]
        }

        manager = ConfigManager()
        manager.load_from_dict(config_dict)

        with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False) as f:
            temp_path = Path(f.name)

        try:
            manager.save_to_file(temp_path, format="yaml")

            # Load it back
            loaded_manager = ConfigManager(temp_path)
            assert loaded_manager.config.version == "1.0.0"
            assert len(loaded_manager.config.projects) == 1

        finally:
            temp_path.unlink()

    def test_validate_method(self):
        """Test configuration validation method."""
        config_dict = {
            "projects": [
                {
                    "name": "valid",
                    "display_name": "Valid",
                    "provider": "gcp",
                    "gcp": {"project_id": "valid-project"}
                }
            ]
        }

        manager = ConfigManager()
        manager.load_from_dict(config_dict)

        assert manager.validate() is True


class TestComplexConfigurations:
    """Test complex configuration scenarios."""

    def test_multi_project_configuration(self):
        """Test configuration with multiple projects."""
        config_dict = {
            "projects": [
                {
                    "name": "prod-us",
                    "display_name": "Production US",
                    "provider": "gcp",
                    "enabled": True,
                    "gcp": {
                        "project_id": "prod-us-project",
                        "monitoring": {
                            "enabled": True,
                            "queries": [
                                {
                                    "name": "CPU",
                                    "query": "avg(cpu)",
                                    "purpose": "CPU monitoring"
                                }
                            ]
                        },
                        "logging": {
                            "enabled": True,
                            "filters": [
                                {
                                    "name": "Errors",
                                    "filter_query": "severity>=ERROR",
                                    "purpose": "Error logs"
                                }
                            ]
                        }
                    },
                    "labels": {
                        "environment": "production",
                        "region": "us-east"
                    }
                },
                {
                    "name": "staging",
                    "display_name": "Staging",
                    "provider": "gcp",
                    "enabled": True,
                    "gcp": {
                        "project_id": "staging-project"
                    }
                }
            ],
            "alerts": {
                "enabled": True,
                "host": "0.0.0.0",
                "port": 5000,
                "max_concurrent_alerts": 20
            }
        }

        manager = ConfigManager()
        config = manager.load_from_dict(config_dict)

        assert len(config.projects) == 2
        assert config.alerts.max_concurrent_alerts == 20

        prod_project = config.get_project("prod-us")
        assert prod_project is not None
        assert len(prod_project.gcp.monitoring.queries) == 1
        assert len(prod_project.gcp.logging.filters) == 1
        assert prod_project.labels["environment"] == "production"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
