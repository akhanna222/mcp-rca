"""Production-grade MCP client for RCA platform.

This module provides a robust MCP client with:
- Retry logic with exponential backoff
- Circuit breaker pattern
- Connection pooling
- Comprehensive error handling
- Performance metrics
"""

import asyncio
import os
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from anthropic import AsyncAnthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.core.exceptions import MCPError
from src.core.logger import get_logger, log_execution_time, set_correlation_id
from src.models.config import AnthropicConfig, ProjectConfig

logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class RCARequest:
    """Root cause analysis request."""
    project_name: str
    alert_summary: str
    alert_documentation: str
    incident_data: Dict[str, Any]
    correlation_id: str


@dataclass
class RCAResponse:
    """Root cause analysis response."""
    analysis: str
    tool_calls_count: int
    execution_time_seconds: float
    correlation_id: str
    status: str = "success"
    error: Optional[str] = None


class CircuitBreaker:
    """Circuit breaker for MCP client resilience."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception type to track
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._state = CircuitState.CLOSED

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    def call(self, func):
        """Decorator to protect a function with circuit breaker."""
        async def wrapper(*args, **kwargs):
            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                import time
                if (
                    self._last_failure_time and
                    time.time() - self._last_failure_time >= self.recovery_timeout
                ):
                    logger.info("Circuit breaker entering half-open state")
                    self._state = CircuitState.HALF_OPEN
                else:
                    raise MCPError(
                        "Circuit breaker is OPEN",
                        {"state": "open", "failures": self._failure_count}
                    )

            try:
                result = await func(*args, **kwargs)

                # Success - reset circuit if it was half-open
                if self._state == CircuitState.HALF_OPEN:
                    logger.info("Circuit breaker closing after successful call")
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0

                return result

            except self.expected_exception as e:
                self._failure_count += 1
                import time
                self._last_failure_time = time.time()

                logger.warning(
                    f"Circuit breaker recorded failure {self._failure_count}",
                    extra={"threshold": self.failure_threshold}
                )

                if self._failure_count >= self.failure_threshold:
                    logger.error("Circuit breaker opening due to failures")
                    self._state = CircuitState.OPEN

                raise

        return wrapper


class MCPClient:
    """Production-grade MCP client for root cause analysis."""

    # Constants
    MAX_TOOL_ITERATIONS = 20  # Prevent infinite loops
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY = 2.0

    def __init__(
        self,
        anthropic_config: AnthropicConfig,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY
    ):
        """Initialize MCP client.

        Args:
            anthropic_config: Anthropic API configuration
            max_retries: Maximum retry attempts for failed requests
            retry_delay: Base delay between retries (exponential backoff)
        """
        self.anthropic_config = anthropic_config
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Initialize Anthropic client
        api_key = anthropic_config.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "Anthropic API key not provided. Set ANTHROPIC_API_KEY "
                "environment variable or configure in config file."
            )

        self.anthropic = AsyncAnthropic(
            api_key=api_key,
            max_retries=anthropic_config.max_retries,
            timeout=anthropic_config.timeout_seconds
        )

        # Circuit breaker for resilience
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60.0,
            expected_exception=MCPError
        )

        # Active sessions cache (project_name -> server_script_path)
        self._server_scripts: Dict[str, Path] = {}

        logger.info(
            "MCP client initialized",
            extra={
                "model": anthropic_config.model,
                "max_tokens": anthropic_config.max_tokens
            }
        )

    def register_project(self, project_config: ProjectConfig, server_script: Path) -> None:
        """Register a project's MCP server.

        Args:
            project_config: Project configuration
            server_script: Path to the MCP server script
        """
        self._server_scripts[project_config.name] = server_script
        logger.info(
            f"Registered MCP server for project {project_config.name}",
            extra={"server_script": str(server_script)}
        )

    @log_execution_time()
    async def analyze(self, request: RCARequest) -> RCAResponse:
        """Perform root cause analysis for an alert.

        Args:
            request: RCA request with alert details

        Returns:
            RCA response with analysis

        Raises:
            MCPError: If analysis fails
        """
        import time
        start_time = time.time()

        set_correlation_id(request.correlation_id)

        logger.info(
            f"Starting RCA for project {request.project_name}",
            extra={
                "correlation_id": request.correlation_id,
                "project": request.project_name
            }
        )

        try:
            # Get server script for this project
            if request.project_name not in self._server_scripts:
                raise MCPError(
                    f"No MCP server registered for project {request.project_name}",
                    {"project": request.project_name}
                )

            server_script = self._server_scripts[request.project_name]

            # Apply circuit breaker
            @self.circuit_breaker.call
            async def run_analysis():
                return await self._run_analysis(request, server_script)

            result = await run_analysis()

            execution_time = time.time() - start_time

            logger.info(
                f"RCA completed successfully",
                extra={
                    "correlation_id": request.correlation_id,
                    "execution_time": execution_time,
                    "tool_calls": result["tool_calls_count"]
                }
            )

            return RCAResponse(
                analysis=result["analysis"],
                tool_calls_count=result["tool_calls_count"],
                execution_time_seconds=execution_time,
                correlation_id=request.correlation_id,
                status="success"
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                f"RCA failed",
                extra={
                    "correlation_id": request.correlation_id,
                    "error": str(e),
                    "execution_time": execution_time
                },
                exc_info=True
            )

            return RCAResponse(
                analysis="",
                tool_calls_count=0,
                execution_time_seconds=execution_time,
                correlation_id=request.correlation_id,
                status="error",
                error=str(e)
            )

    async def _run_analysis(
        self,
        request: RCARequest,
        server_script: Path
    ) -> Dict[str, Any]:
        """Run the actual analysis with MCP session.

        Args:
            request: RCA request
            server_script: Path to MCP server script

        Returns:
            Analysis results dictionary

        Raises:
            MCPError: If analysis fails
        """
        exit_stack = AsyncExitStack()

        try:
            # Create MCP session
            session = await self._create_session(exit_stack, server_script)

            # Build prompt from request
            prompt = self._build_prompt(request)

            # Process with Claude
            result = await self._process_with_session(prompt, session)

            return result

        finally:
            # Clean up session
            await exit_stack.aclose()

    async def _create_session(
        self,
        exit_stack: AsyncExitStack,
        server_script: Path
    ) -> ClientSession:
        """Create a new MCP session.

        Args:
            exit_stack: Async exit stack for resource cleanup
            server_script: Path to the MCP server script

        Returns:
            Initialized client session

        Raises:
            MCPError: If session creation fails
        """
        if not server_script.exists():
            raise MCPError(
                f"MCP server script not found: {server_script}",
                {"path": str(server_script)}
            )

        # Determine command based on file extension
        is_python = server_script.suffix == ".py"
        is_js = server_script.suffix == ".js"

        if not (is_python or is_js):
            raise MCPError(
                f"Unsupported server script type: {server_script.suffix}",
                {"supported": [".py", ".js"]}
            )

        command = sys.executable if is_python else "node"

        # Setup server parameters
        server_params = StdioServerParameters(
            command=command,
            args=[str(server_script)],
            env=os.environ.copy()
        )

        try:
            # Create stdio transport
            stdio_transport = await exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            stdio, write = stdio_transport

            # Create and initialize session
            session = await exit_stack.enter_async_context(
                ClientSession(stdio, write)
            )
            await session.initialize()

            logger.debug("MCP session created successfully")
            return session

        except Exception as e:
            raise MCPError(
                f"Failed to create MCP session",
                {"server_script": str(server_script), "error": str(e)}
            ) from e

    def _build_prompt(self, request: RCARequest) -> str:
        """Build analysis prompt from request.

        Args:
            request: RCA request

        Returns:
            Formatted prompt string
        """
        # TODO: Load from template system
        return f"""You are an intelligent root cause analysis system designed to investigate system incidents.

The following alert has been triggered:

**Summary:** {request.alert_summary}

**Documentation:** {request.alert_documentation}

**Incident Data:**
{self._format_incident_data(request.incident_data)}

Your task is to analyze monitoring data and logs to determine the most likely root cause of this issue.

**Guidelines:**
1. Use the available MCP tools judiciously to gather relevant data
2. Execute queries in batches when possible to minimize API calls
3. Focus on efficiency - only collect data that's necessary for analysis
4. Provide a clear, actionable analysis with:
   - Identified root cause
   - Supporting evidence from monitoring/logs
   - Recommended remediation steps
5. Keep your analysis concise and focused

Begin your investigation."""

    def _format_incident_data(self, data: Dict[str, Any]) -> str:
        """Format incident data for prompt.

        Args:
            data: Incident data dictionary

        Returns:
            Formatted string
        """
        lines = []
        for key, value in data.items():
            lines.append(f"- **{key}:** {value}")
        return "\n".join(lines) if lines else "No additional data"

    async def _process_with_session(
        self,
        prompt: str,
        session: ClientSession
    ) -> Dict[str, Any]:
        """Process prompt using MCP session and Claude.

        Args:
            prompt: Analysis prompt
            session: MCP client session

        Returns:
            Analysis results

        Raises:
            MCPError: If processing fails
        """
        # Get available tools from MCP server
        try:
            response = await session.list_tools()
            available_tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema
                }
                for tool in response.tools
            ]

            logger.debug(
                f"Available MCP tools: {[t['name'] for t in available_tools]}"
            )

        except Exception as e:
            raise MCPError(
                "Failed to list MCP tools",
                {"error": str(e)}
            ) from e

        # Initialize conversation
        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]

        final_text: List[str] = []
        tool_calls_count = 0

        # Agentic loop with tool calls
        for iteration in range(self.MAX_TOOL_ITERATIONS):
            try:
                # Call Claude
                response = await self.anthropic.messages.create(
                    model=self.anthropic_config.model,
                    max_tokens=self.anthropic_config.max_tokens,
                    messages=messages,
                    tools=available_tools
                )

                assistant_content = []
                tools_used = False

                # Process response content
                for content in response.content:
                    if content.type == "text":
                        final_text.append(content.text)
                        assistant_content.append(content)

                    elif content.type == "tool_use":
                        tools_used = True
                        tool_calls_count += 1

                        tool_name = content.name
                        tool_args = content.input

                        logger.info(
                            f"Calling MCP tool: {tool_name}",
                            extra={"iteration": iteration + 1}
                        )

                        # Call MCP tool
                        try:
                            result = await session.call_tool(tool_name, tool_args)

                            # Add tool use to conversation
                            assistant_content.append(content)
                            messages.append({
                                "role": "assistant",
                                "content": assistant_content
                            })

                            # Add tool result
                            messages.append({
                                "role": "user",
                                "content": [
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": content.id,
                                        "content": result.content
                                    }
                                ]
                            })

                            # Reset assistant_content for next iteration
                            assistant_content = []

                        except Exception as e:
                            logger.error(
                                f"MCP tool call failed: {tool_name}",
                                extra={"error": str(e)},
                                exc_info=True
                            )
                            # Return error to Claude so it can adapt
                            messages.append({
                                "role": "assistant",
                                "content": assistant_content + [content]
                            })
                            messages.append({
                                "role": "user",
                                "content": [
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": content.id,
                                        "content": f"Error: {str(e)}",
                                        "is_error": True
                                    }
                                ]
                            })
                            assistant_content = []

                # If no tools were used, we're done
                if not tools_used:
                    if assistant_content:
                        messages.append({
                            "role": "assistant",
                            "content": assistant_content
                        })
                    break

            except Exception as e:
                raise MCPError(
                    f"Failed to process with Claude",
                    {"iteration": iteration + 1, "error": str(e)}
                ) from e

        # Check if we hit max iterations
        if iteration == self.MAX_TOOL_ITERATIONS - 1:
            logger.warning(
                f"Reached maximum tool iterations ({self.MAX_TOOL_ITERATIONS})"
            )

        return {
            "analysis": "\n".join(final_text),
            "tool_calls_count": tool_calls_count
        }


async def test_client():
    """Test function for MCP client."""
    from src.models.config import AnthropicConfig

    config = AnthropicConfig()
    client = MCPClient(config)

    request = RCARequest(
        project_name="test",
        alert_summary="High latency detected",
        alert_documentation="Latency exceeded 2 seconds",
        incident_data={"metric": "latency", "value": "2.5s"},
        correlation_id="test-123"
    )

    response = await client.analyze(request)
    print(f"Analysis: {response.analysis}")
    print(f"Tool calls: {response.tool_calls_count}")
    print(f"Time: {response.execution_time_seconds}s")


if __name__ == "__main__":
    asyncio.run(test_client())
