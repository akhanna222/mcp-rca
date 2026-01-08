"""Configuration models for the multi-project RCA platform.

This module defines Pydantic models for validating and managing configuration
for multiple cloud projects, monitoring sources, and alert integrations.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class CloudProvider(str, Enum):
    """Supported cloud providers."""

    GCP = "gcp"
    AWS = "aws"
    AZURE = "azure"
    MULTI = "multi"


class AuthMethod(str, Enum):
    """Authentication methods for cloud providers."""

    SERVICE_ACCOUNT = "service_account"
    DEFAULT_CREDENTIALS = "default_credentials"
    IAM_ROLE = "iam_role"
    MANAGED_IDENTITY = "managed_identity"
    ENVIRONMENT = "environment"


class GCPAuth(BaseModel):
    """GCP authentication configuration."""

    method: AuthMethod = Field(
        default=AuthMethod.DEFAULT_CREDENTIALS,
        description="Authentication method for GCP"
    )
    service_account_path: Optional[Path] = Field(
        default=None,
        description="Path to service account JSON file"
    )
    quota_project_id: Optional[str] = Field(
        default=None,
        description="Project ID for API quota billing"
    )
    scopes: List[str] = Field(
        default=["https://www.googleapis.com/auth/cloud-platform"],
        description="OAuth2 scopes for authentication"
    )

    @field_validator("service_account_path")
    @classmethod
    def validate_service_account_path(cls, v: Optional[Path]) -> Optional[Path]:
        """Validate service account file exists if specified."""
        if v is not None and not v.exists():
            raise ValueError(f"Service account file not found: {v}")
        return v


class AWSAuth(BaseModel):
    """AWS authentication configuration."""

    method: AuthMethod = Field(
        default=AuthMethod.ENVIRONMENT,
        description="Authentication method for AWS"
    )
    profile: Optional[str] = Field(
        default=None,
        description="AWS profile name from ~/.aws/credentials"
    )
    region: str = Field(
        default="us-east-1",
        description="AWS region"
    )
    access_key_id: Optional[str] = Field(
        default=None,
        description="AWS access key ID (not recommended, use IAM roles)"
    )
    secret_access_key: Optional[str] = Field(
        default=None,
        description="AWS secret access key (not recommended, use IAM roles)"
    )


class AzureAuth(BaseModel):
    """Azure authentication configuration."""

    method: AuthMethod = Field(
        default=AuthMethod.MANAGED_IDENTITY,
        description="Authentication method for Azure"
    )
    tenant_id: Optional[str] = Field(
        default=None,
        description="Azure AD tenant ID"
    )
    client_id: Optional[str] = Field(
        default=None,
        description="Service principal client ID"
    )
    client_secret: Optional[str] = Field(
        default=None,
        description="Service principal client secret"
    )


class MonitoringQuery(BaseModel):
    """Individual monitoring query definition."""

    name: str = Field(..., description="Human-readable name for the query")
    query: str = Field(..., description="The actual query string (PromQL, etc.)")
    purpose: str = Field(..., description="What this query is meant to discover")
    enabled: bool = Field(default=True, description="Whether this query is active")


class MonitoringConfig(BaseModel):
    """Monitoring configuration for a project."""

    enabled: bool = Field(default=True, description="Enable monitoring data collection")
    queries: List[MonitoringQuery] = Field(
        default_factory=list,
        description="List of monitoring queries to execute"
    )
    timeout_seconds: float = Field(
        default=60.0,
        description="Timeout for monitoring queries",
        gt=0,
        le=300
    )
    max_concurrent_queries: int = Field(
        default=10,
        description="Maximum concurrent queries",
        gt=0,
        le=50
    )


class LogFilter(BaseModel):
    """Log filter definition."""

    name: str = Field(..., description="Human-readable name for the filter")
    filter_query: str = Field(..., description="The log filter query")
    purpose: str = Field(..., description="What this filter is meant to find")
    enabled: bool = Field(default=True, description="Whether this filter is active")


class LoggingConfig(BaseModel):
    """Logging configuration for a project."""

    enabled: bool = Field(default=True, description="Enable log data collection")
    filters: List[LogFilter] = Field(
        default_factory=list,
        description="List of log filters to apply"
    )
    default_time_range_minutes: float = Field(
        default=10.0,
        description="Default time range for log queries in minutes",
        gt=0,
        le=1440  # 24 hours max
    )
    max_log_entries: int = Field(
        default=1000,
        description="Maximum log entries to retrieve",
        gt=0,
        le=10000
    )
    timeout_seconds: float = Field(
        default=60.0,
        description="Timeout for log queries",
        gt=0,
        le=300
    )


class GCPConfig(BaseModel):
    """Google Cloud Platform specific configuration."""

    project_id: str = Field(..., description="GCP project ID")
    auth: GCPAuth = Field(default_factory=GCPAuth, description="GCP authentication")
    monitoring: MonitoringConfig = Field(
        default_factory=MonitoringConfig,
        description="Monitoring configuration"
    )
    logging: LoggingConfig = Field(
        default_factory=LoggingConfig,
        description="Logging configuration"
    )


class AWSConfig(BaseModel):
    """AWS specific configuration."""

    account_id: str = Field(..., description="AWS account ID")
    auth: AWSAuth = Field(default_factory=AWSAuth, description="AWS authentication")
    monitoring: MonitoringConfig = Field(
        default_factory=MonitoringConfig,
        description="Monitoring configuration"
    )
    logging: LoggingConfig = Field(
        default_factory=LoggingConfig,
        description="Logging configuration"
    )


class AzureConfig(BaseModel):
    """Azure specific configuration."""

    subscription_id: str = Field(..., description="Azure subscription ID")
    auth: AzureAuth = Field(default_factory=AzureAuth, description="Azure authentication")
    monitoring: MonitoringConfig = Field(
        default_factory=MonitoringConfig,
        description="Monitoring configuration"
    )
    logging: LoggingConfig = Field(
        default_factory=LoggingConfig,
        description="Logging configuration"
    )


class ProjectConfig(BaseModel):
    """Configuration for a single project/environment."""

    name: str = Field(..., description="Unique project identifier")
    display_name: str = Field(..., description="Human-readable project name")
    description: Optional[str] = Field(
        default=None,
        description="Project description"
    )
    provider: CloudProvider = Field(..., description="Cloud provider")
    enabled: bool = Field(default=True, description="Enable monitoring for this project")

    # Cloud-specific configurations
    gcp: Optional[GCPConfig] = Field(default=None, description="GCP configuration")
    aws: Optional[AWSConfig] = Field(default=None, description="AWS configuration")
    azure: Optional[AzureConfig] = Field(default=None, description="Azure configuration")

    # Custom labels for filtering and organization
    labels: Dict[str, str] = Field(
        default_factory=dict,
        description="Custom labels for project organization"
    )

    # Alert routing
    alert_routing: Dict[str, Any] = Field(
        default_factory=dict,
        description="Alert routing configuration"
    )

    @model_validator(mode='after')
    def validate_provider_config(self) -> 'ProjectConfig':
        """Ensure the appropriate cloud config is present for the provider."""
        provider_config_map = {
            CloudProvider.GCP: self.gcp,
            CloudProvider.AWS: self.aws,
            CloudProvider.AZURE: self.azure,
        }

        if self.provider != CloudProvider.MULTI:
            if provider_config_map.get(self.provider) is None:
                raise ValueError(
                    f"Provider '{self.provider}' requires corresponding config section"
                )

        return self


class AnthropicConfig(BaseModel):
    """Anthropic API configuration."""

    api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key (prefer env var ANTHROPIC_API_KEY)"
    )
    model: str = Field(
        default="claude-3-7-sonnet-20250219",
        description="Claude model to use"
    )
    max_tokens: int = Field(
        default=8192,
        description="Maximum tokens per request",
        gt=0,
        le=200000
    )
    timeout_seconds: float = Field(
        default=300.0,
        description="API request timeout",
        gt=0
    )
    max_retries: int = Field(
        default=3,
        description="Maximum API retries",
        ge=0,
        le=10
    )


class AlertConfig(BaseModel):
    """Alert webhook configuration."""

    enabled: bool = Field(default=True, description="Enable alert processing")
    host: str = Field(default="0.0.0.0", description="Webhook server host")
    port: int = Field(default=5000, description="Webhook server port", gt=0, le=65535)
    path: str = Field(default="/alert", description="Webhook endpoint path")
    auth_token: Optional[str] = Field(
        default=None,
        description="Bearer token for webhook authentication"
    )
    max_concurrent_alerts: int = Field(
        default=10,
        description="Maximum concurrent alert processing",
        gt=0,
        le=100
    )


class ObservabilityConfig(BaseModel):
    """Observability configuration for the platform itself."""

    enabled: bool = Field(default=True, description="Enable platform observability")
    metrics_port: int = Field(
        default=9090,
        description="Prometheus metrics port",
        gt=0,
        le=65535
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"
    )
    log_format: str = Field(
        default="json",
        description="Log format (json or text)",
        pattern="^(json|text)$"
    )
    structured_logging: bool = Field(
        default=True,
        description="Use structured logging"
    )
    trace_enabled: bool = Field(
        default=False,
        description="Enable distributed tracing"
    )


class PlatformConfig(BaseSettings):
    """Main platform configuration."""

    version: str = Field(default="1.0.0", description="Configuration version")

    # Projects configuration
    projects: List[ProjectConfig] = Field(
        default_factory=list,
        description="List of projects to monitor"
    )

    # Anthropic configuration
    anthropic: AnthropicConfig = Field(
        default_factory=AnthropicConfig,
        description="Anthropic API configuration"
    )

    # Alert configuration
    alerts: AlertConfig = Field(
        default_factory=AlertConfig,
        description="Alert webhook configuration"
    )

    # Platform observability
    observability: ObservabilityConfig = Field(
        default_factory=ObservabilityConfig,
        description="Platform observability configuration"
    )

    # Prompt templates directory
    prompt_templates_dir: Path = Field(
        default=Path("./prompts"),
        description="Directory containing prompt templates"
    )

    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"
        extra = "allow"

    @field_validator("projects")
    @classmethod
    def validate_unique_project_names(cls, v: List[ProjectConfig]) -> List[ProjectConfig]:
        """Ensure project names are unique."""
        names = [p.name for p in v]
        if len(names) != len(set(names)):
            raise ValueError("Project names must be unique")
        return v

    def get_project(self, name: str) -> Optional[ProjectConfig]:
        """Get project configuration by name."""
        return next((p for p in self.projects if p.name == name), None)

    def get_enabled_projects(self) -> List[ProjectConfig]:
        """Get all enabled projects."""
        return [p for p in self.projects if p.enabled]
