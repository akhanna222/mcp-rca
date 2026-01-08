"""Prompt template management for RCA platform.

This module provides dynamic prompt generation based on project
configuration, monitoring queries, and log filters.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound

from src.core.exceptions import ConfigurationError
from src.core.logger import get_logger
from src.models.config import ProjectConfig

logger = get_logger(__name__)


class PromptManager:
    """Manager for prompt templates.

    Handles loading, rendering, and customizing prompts based on
    project configuration and alert context.
    """

    # Default template if none specified
    DEFAULT_TEMPLATE = """You are an intelligent root cause analysis system designed to investigate system incidents.

The following alert has been triggered:

**Alert Summary:** {{ alert_summary }}

**Documentation:** {{ alert_documentation }}

{% if incident_data %}
**Incident Data:**
{% for key, value in incident_data.items() %}
- **{{ key }}:** {{ value }}
{% endfor %}
{% endif %}

Your task is to analyze monitoring data and logs to determine the most likely root cause of this issue.

{% if monitoring_queries %}
## Available Monitoring Queries
Use these monitoring queries sparingly and strategically to gather relevant data. Execute queries in batch when possible:

{% for query in monitoring_queries %}
{{ loop.index }}. **{{ query.name }}** ({{ query.purpose }}):
   `{{ query.query }}`
{% endfor %}
{% endif %}

{% if log_filters %}
## Available Log Filters
Use these log filters to retrieve relevant error logs (recommended time range: ≤10 minutes):

{% for filter in log_filters %}
{{ loop.index }}. **{{ filter.name }}** ({{ filter.purpose }}):
   `{{ filter.filter_query }}`
{% endfor %}
{% endif %}

## Guidelines
1. **Be Strategic:** Only query data that's necessary for root cause analysis
2. **Batch Operations:** Execute multiple queries together when possible
3. **Focus on Evidence:** Look for clear signals in metrics and logs
4. **Be Efficient:** Minimize API calls and token usage
5. **Provide Actionable Insights:**
   - Identify the root cause with supporting evidence
   - Explain the causal chain of events
   - Suggest specific remediation steps
   - Indicate if the issue is still ongoing or resolved

{% if project_context %}
## Project Context
{{ project_context }}
{% endif %}

Begin your investigation. Remember: be thorough but efficient."""

    def __init__(self, templates_dir: Optional[Path] = None):
        """Initialize prompt manager.

        Args:
            templates_dir: Directory containing Jinja2 templates
        """
        self.templates_dir = templates_dir

        # Setup Jinja2 environment if templates directory provided
        if templates_dir and templates_dir.exists():
            self.env = Environment(
                loader=FileSystemLoader(str(templates_dir)),
                trim_blocks=True,
                lstrip_blocks=True,
                autoescape=False
            )
            logger.info(f"Initialized prompt manager with templates from {templates_dir}")
        else:
            self.env = None
            logger.info("Initialized prompt manager with default template")

    def build_prompt(
        self,
        project_config: ProjectConfig,
        alert_summary: str,
        alert_documentation: str,
        incident_data: Optional[Dict[str, Any]] = None,
        template_name: Optional[str] = None,
        **extra_context: Any
    ) -> str:
        """Build RCA prompt for a project.

        Args:
            project_config: Project configuration
            alert_summary: Alert summary text
            alert_documentation: Alert documentation
            incident_data: Additional incident data
            template_name: Optional custom template name
            **extra_context: Additional template context

        Returns:
            Rendered prompt string

        Raises:
            ConfigurationError: If template rendering fails
        """
        logger.debug(
            f"Building prompt for project {project_config.name}",
            extra={"template": template_name or "default"}
        )

        try:
            # Get template
            template = self._get_template(template_name)

            # Build context
            context = self._build_context(
                project_config,
                alert_summary,
                alert_documentation,
                incident_data,
                **extra_context
            )

            # Render template
            prompt = template.render(**context)

            logger.debug(
                f"Prompt built successfully",
                extra={"length": len(prompt)}
            )

            return prompt

        except Exception as e:
            raise ConfigurationError(
                f"Failed to build prompt",
                {
                    "project": project_config.name,
                    "template": template_name,
                    "error": str(e)
                }
            ) from e

    def _get_template(self, template_name: Optional[str] = None) -> Template:
        """Get Jinja2 template.

        Args:
            template_name: Optional template name

        Returns:
            Jinja2 template

        Raises:
            ConfigurationError: If template not found
        """
        if template_name and self.env:
            try:
                return self.env.get_template(template_name)
            except TemplateNotFound:
                logger.warning(
                    f"Template '{template_name}' not found, using default"
                )

        # Use default template
        from jinja2 import Template
        return Template(self.DEFAULT_TEMPLATE)

    def _build_context(
        self,
        project_config: ProjectConfig,
        alert_summary: str,
        alert_documentation: str,
        incident_data: Optional[Dict[str, Any]] = None,
        **extra_context: Any
    ) -> Dict[str, Any]:
        """Build template context from project config and alert data.

        Args:
            project_config: Project configuration
            alert_summary: Alert summary
            alert_documentation: Alert documentation
            incident_data: Incident data
            **extra_context: Additional context

        Returns:
            Template context dictionary
        """
        context = {
            "project_name": project_config.name,
            "project_display_name": project_config.display_name,
            "provider": project_config.provider.value,
            "alert_summary": alert_summary,
            "alert_documentation": alert_documentation,
            "incident_data": incident_data or {},
        }

        # Add monitoring queries if available
        if project_config.provider.value == "gcp" and project_config.gcp:
            monitoring_config = project_config.gcp.monitoring
            if monitoring_config.enabled:
                context["monitoring_queries"] = [
                    {
                        "name": q.name,
                        "query": q.query,
                        "purpose": q.purpose
                    }
                    for q in monitoring_config.queries
                    if q.enabled
                ]

            # Add log filters
            logging_config = project_config.gcp.logging
            if logging_config.enabled:
                context["log_filters"] = [
                    {
                        "name": f.name,
                        "filter_query": f.filter_query,
                        "purpose": f.purpose
                    }
                    for f in logging_config.filters
                    if f.enabled
                ]

        # TODO: Add support for AWS and Azure

        # Add project-specific context from description
        if project_config.description:
            context["project_context"] = project_config.description

        # Add labels as context
        if project_config.labels:
            context["labels"] = project_config.labels

        # Merge extra context
        context.update(extra_context)

        return context

    def load_template_from_file(self, template_path: Path) -> str:
        """Load template content from a file.

        Args:
            template_path: Path to template file

        Returns:
            Template content

        Raises:
            ConfigurationError: If file doesn't exist or can't be read
        """
        if not template_path.exists():
            raise ConfigurationError(
                f"Template file not found: {template_path}",
                {"path": str(template_path)}
            )

        try:
            return template_path.read_text(encoding="utf-8")
        except Exception as e:
            raise ConfigurationError(
                f"Failed to read template file",
                {"path": str(template_path), "error": str(e)}
            ) from e

    def save_template(self, name: str, content: str) -> None:
        """Save a template to the templates directory.

        Args:
            name: Template name (filename)
            content: Template content

        Raises:
            ConfigurationError: If templates directory is not configured
        """
        if not self.templates_dir:
            raise ConfigurationError(
                "Templates directory not configured",
                {"message": "Provide templates_dir when initializing PromptManager"}
            )

        self.templates_dir.mkdir(parents=True, exist_ok=True)

        template_path = self.templates_dir / name
        try:
            template_path.write_text(content, encoding="utf-8")
            logger.info(f"Template saved: {template_path}")

            # Reload Jinja2 environment
            if self.env:
                self.env = Environment(
                    loader=FileSystemLoader(str(self.templates_dir)),
                    trim_blocks=True,
                    lstrip_blocks=True,
                    autoescape=False
                )

        except Exception as e:
            raise ConfigurationError(
                f"Failed to save template",
                {"path": str(template_path), "error": str(e)}
            ) from e


def create_default_prompt_manager(templates_dir: Optional[Path] = None) -> PromptManager:
    """Create a prompt manager with default configuration.

    Args:
        templates_dir: Optional templates directory

    Returns:
        Initialized PromptManager
    """
    if templates_dir is None:
        # Try default location
        default_path = Path("prompts")
        if default_path.exists():
            templates_dir = default_path

    return PromptManager(templates_dir)
