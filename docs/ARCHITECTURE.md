# MCP-RCA Platform Architecture

## Executive Summary

MCP-RCA is a production-grade, cloud-native platform for automated root cause analysis. Built on the Model Context Protocol and powered by Claude AI, it provides intelligent incident analysis across multiple cloud providers with enterprise-level reliability and observability.

---

## Architecture Principles

### 1. **Separation of Concerns**
Each component has a single, well-defined responsibility:
- **API Layer**: HTTP/webhook handling, routing
- **MCP Client**: Claude orchestration, tool coordination
- **MCP Servers**: Cloud provider integration, data retrieval
- **Core Services**: Configuration, logging, exception handling

### 2. **Fail-Safe by Default**
- Circuit breakers prevent cascade failures
- Exponential backoff for transient errors
- Graceful degradation when services unavailable
- Comprehensive error context for debugging

### 3. **Observable by Design**
- Structured logging with correlation IDs
- Prometheus metrics for all operations
- Request tracing across components
- Performance instrumentation

### 4. **Configuration as Code**
- Declarative YAML/JSON configuration
- Schema validation with Pydantic
- Version-controlled configurations
- Environment variable support

### 5. **Extensibility First**
- Abstract base classes for providers
- Plugin-based architecture
- Clean interfaces for integration
- Minimal coupling between components

---

## System Architecture

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                   Alert Sources                         │
│  (Cloud Monitoring, Prometheus, PagerDuty, Custom)     │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP POST /alert
                       ▼
┌─────────────────────────────────────────────────────────┐
│              API Server (Quart/ASGI)                    │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Request Validation & Authentication             │  │
│  └──────────────────┬───────────────────────────────┘  │
│                     │                                    │
│  ┌──────────────────▼───────────────────────────────┐  │
│  │  Alert Router                                     │  │
│  │  - Project Detection                              │  │
│  │  - Correlation ID Generation                      │  │
│  │  - Context Setup                                  │  │
│  └──────────────────┬───────────────────────────────┘  │
│                     │                                    │
│  ┌──────────────────▼───────────────────────────────┐  │
│  │  Concurrent Processor                             │  │
│  │  - Semaphore-based Concurrency Control           │  │
│  │  - Async Task Queue                               │  │
│  │  - Load Balancing                                 │  │
│  └──────────────────┬───────────────────────────────┘  │
└────────────────────│────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              MCP Client Layer                           │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Circuit Breaker                                  │  │
│  │  - State: CLOSED | OPEN | HALF_OPEN             │  │
│  │  - Failure Threshold: 5                           │  │
│  │  - Recovery Timeout: 60s                          │  │
│  └──────────────────┬───────────────────────────────┘  │
│                     │                                    │
│  ┌──────────────────▼───────────────────────────────┐  │
│  │  Session Manager                                  │  │
│  │  - Per-Request Session Creation                  │  │
│  │  - Connection Pooling                             │  │
│  │  - Resource Cleanup                               │  │
│  └──────────────────┬───────────────────────────────┘  │
│                     │                                    │
│  ┌──────────────────▼───────────────────────────────┐  │
│  │  Anthropic Claude Client                          │  │
│  │  - Model: claude-3-7-sonnet-20250219            │  │
│  │  - Max Tokens: 8192                               │  │
│  │  - Agentic Loop with Tool Calls                   │  │
│  └──────────────────┬───────────────────────────────┘  │
└────────────────────│────────────────────────────────────┘
                     │ stdio Transport (subprocess)
                     ▼
┌─────────────────────────────────────────────────────────┐
│              MCP Server Layer                           │
│  (One Process Per Project)                              │
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │  GCP Observability Server                      │    │
│  │  ┌──────────────────────────────────────────┐  │    │
│  │  │  Authentication                           │  │    │
│  │  │  - Service Account / Default Credentials │  │    │
│  │  │  - Token Refresh Logic                    │  │    │
│  │  └──────────────────────────────────────────┘  │    │
│  │  ┌──────────────────────────────────────────┐  │    │
│  │  │  HTTP Client Pool                         │  │    │
│  │  │  - Connection Reuse                       │  │    │
│  │  │  - Configurable Timeouts                  │  │    │
│  │  │  - Retry with Exponential Backoff         │  │    │
│  │  └──────────────────────────────────────────┘  │    │
│  │  ┌──────────────────────────────────────────┐  │    │
│  │  │  Tools                                     │  │    │
│  │  │  - get_gcp_monitoring_data()              │  │    │
│  │  │  - get_gcp_logs()                         │  │    │
│  │  └──────────────────────────────────────────┘  │    │
│  └────────────────────────────────────────────────┘    │
│                     │                                    │
└────────────────────│────────────────────────────────────┘
                     │ HTTPS
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Cloud Provider APIs                        │
│  - Google Cloud Monitoring (Prometheus API)             │
│  - Google Cloud Logging                                 │
│  - AWS CloudWatch (future)                              │
│  - Azure Monitor (future)                               │
└─────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────┐
│              Supporting Services                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Configuration Manager                            │  │
│  │  - YAML/JSON Parsing                              │  │
│  │  - Pydantic Validation                            │  │
│  │  - Hot Reload Support                             │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Structured Logger                                │  │
│  │  - JSON/Text Format                               │  │
│  │  - Correlation ID Injection                       │  │
│  │  - Context Variables                              │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Prometheus Metrics                               │  │
│  │  - Counter: alerts_received_total                │  │
│  │  - Gauge: alerts_processing                      │  │
│  │  - Histogram: processing_duration                │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. API Server (`src/api/server.py`)

**Responsibilities**:
- Accept webhook alerts via HTTP POST
- Validate and authenticate requests
- Route alerts to appropriate projects
- Manage concurrent request processing
- Expose health and metrics endpoints

**Technology Stack**:
- **Quart**: Async web framework (Flask-like API)
- **Prometheus Client**: Metrics collection
- **asyncio**: Concurrent request handling

**Key Design Decisions**:

#### Async-First Design
- Uses `async`/`await` for all I/O operations
- Non-blocking alert processing
- Efficient resource utilization
- Scales to thousands of concurrent alerts

#### Semaphore-Based Concurrency Control
```python
# From src/api/server.py
self.processing_semaphore = asyncio.Semaphore(
    self.config.alerts.max_concurrent_alerts
)

async with self.processing_semaphore:
    # Process alert with bounded concurrency
    response = await self.mcp_client.analyze(rca_request)
```

**Why**: Prevents resource exhaustion from alert storms

#### Fire-and-Forget Processing
```python
# Alert accepted immediately, processed asynchronously
asyncio.create_task(
    rca_server.process_alert(alert_data, project_name)
)
return jsonify({"status": "accepted"}), 202
```

**Why**: Webhook must respond quickly (< 5s) to avoid timeouts

**Endpoints**:
- `POST /alert`: Alert webhook (returns 202 Accepted)
- `GET /health`: Health check
- `GET /metrics`: Prometheus metrics
- `GET /projects`: List configured projects

---

### 2. MCP Client (`src/mcp_client/client.py`)

**Responsibilities**:
- Manage Claude API interactions
- Orchestrate MCP tool calls
- Handle session lifecycle
- Implement resilience patterns

**Technology Stack**:
- **Anthropic SDK**: Claude API client
- **MCP SDK**: Model Context Protocol
- **asyncio**: Async operations

**Key Design Patterns**:

#### Circuit Breaker Pattern
```python
class CircuitBreaker:
    """Prevents cascade failures."""

    States:
    - CLOSED: Normal operation
    - OPEN: Failing, reject requests
    - HALF_OPEN: Testing recovery

    Parameters:
    - failure_threshold: 5 failures
    - recovery_timeout: 60 seconds
```

**Why**: Fail fast when Claude API is unavailable, allow recovery

#### Per-Request Session Management
```python
async def process_query(self, query: str) -> str:
    exit_stack = AsyncExitStack()
    session = await self._create_session(exit_stack)

    try:
        return await self._process_with_session(query, session)
    finally:
        await exit_stack.aclose()  # Always cleanup
```

**Why**: Isolate failures, prevent resource leaks

#### Agentic Loop with Tool Calls
```python
for iteration in range(MAX_TOOL_ITERATIONS):
    response = await anthropic.messages.create(...)

    for content in response.content:
        if content.type == "tool_use":
            result = await session.call_tool(...)
            # Add result to conversation
        elif content.type == "text":
            # Collect final analysis

    if not tools_used:
        break  # Done
```

**Why**: Allow Claude to iteratively gather data until confident

---

### 3. MCP Servers (`src/mcp_servers/`)

**Responsibilities**:
- Authenticate with cloud providers
- Query monitoring metrics
- Retrieve log entries
- Expose tools via MCP protocol

**Architecture**:

#### Abstract Base Class Pattern
```python
class ObservabilityServer(ABC):
    """Base class for all cloud providers."""

    @abstractmethod
    async def query_metrics(...): pass

    @abstractmethod
    async def query_logs(...): pass

    @abstractmethod
    async def authenticate(...): pass
```

**Why**: Enforce consistent interface, enable polymorphism

#### GCP Implementation
- **Authentication**: Supports service accounts and ADC
- **Monitoring**: Prometheus-compatible API
- **Logging**: Cloud Logging with deduplication
- **HTTP Client**: Connection pooling with httpx

**Key Features**:
- Concurrent query execution with semaphore
- Exponential backoff for retries
- Token refresh automation
- Structured error responses

**Tool Registration**:
```python
@mcp.tool()
async def get_gcp_monitoring_data(
    promql_queries: List[List[str]]
) -> List[Dict[str, Any]]:
    """Query monitoring metrics from GCP."""
    # Tool implementation
```

**Communication**: Stdio transport (subprocess)

---

### 4. Configuration Management (`src/core/config_manager.py`)

**Responsibilities**:
- Load configuration from YAML/JSON
- Validate using Pydantic models
- Provide configuration access
- Support environment variables

**Schema Hierarchy**:
```
PlatformConfig
├── anthropic: AnthropicConfig
├── alerts: AlertConfig
├── observability: ObservabilityConfig
└── projects: List[ProjectConfig]
    ├── gcp: GCPConfig
    │   ├── auth: GCPAuth
    │   ├── monitoring: MonitoringConfig
    │   │   └── queries: List[MonitoringQuery]
    │   └── logging: LoggingConfig
    │       └── filters: List[LogFilter]
    ├── aws: AWSConfig (future)
    └── azure: AzureConfig (future)
```

**Validation Features**:
- Type checking at runtime
- Field validation (ranges, patterns)
- Cross-field validation
- Unique constraints
- Required field checks

**Example Validation**:
```python
class MonitoringConfig(BaseModel):
    timeout_seconds: float = Field(gt=0, le=300)
    # Must be > 0 and <= 300
```

---

### 5. Structured Logging (`src/core/logger.py`)

**Responsibilities**:
- Structured JSON logging
- Correlation ID tracking
- Context injection
- Performance instrumentation

**Context Variables** (thread-local):
```python
correlation_id_var: ContextVar[Optional[str]]
project_name_var: ContextVar[Optional[str]]
```

**Log Format**:
```json
{
  "timestamp": "2026-01-08T12:00:00Z",
  "level": "INFO",
  "correlation_id": "a1b2c3d4",
  "project": "prod-us-east",
  "module": "src.api.server",
  "function": "process_alert",
  "line": 123,
  "message": "Alert processed successfully",
  "execution_time_seconds": 12.5,
  "tool_calls": 3
}
```

**Decorator for Performance**:
```python
@log_execution_time()
async def expensive_operation():
    # Automatically logs execution time
```

---

## Data Flow

### Alert Processing Flow

1. **Alert Received**
   - HTTP POST to `/alert`
   - Request validation
   - Authentication check
   - Correlation ID generated

2. **Project Detection**
   - Extract project from payload
   - Lookup project configuration
   - Validate project is enabled

3. **Prompt Generation**
   - Load prompt template
   - Inject project-specific queries/filters
   - Format alert data
   - Generate analysis prompt

4. **MCP Session**
   - Create subprocess for MCP server
   - Initialize stdio transport
   - Authenticate with cloud provider
   - List available tools

5. **Agentic Loop**
   - Send prompt to Claude
   - Claude requests tools (metrics/logs)
   - Execute tools via MCP server
   - Return results to Claude
   - Repeat until analysis complete

6. **Response**
   - Extract RCA from Claude response
   - Log analysis result
   - Update metrics
   - Return status to webhook caller

**Timing Breakdown** (typical):
- Alert received: T+0ms
- Webhook response: T+50ms (202 Accepted)
- Session creation: T+500ms
- First tool call: T+2000ms
- Analysis complete: T+15000ms
- Metrics updated: T+15050ms

---

## Resilience Patterns

### 1. Circuit Breaker
- **Purpose**: Prevent cascade failures
- **Implementation**: `CircuitBreaker` class
- **States**: CLOSED → OPEN → HALF_OPEN → CLOSED
- **Thresholds**: 5 failures, 60s recovery

### 2. Exponential Backoff
- **Purpose**: Handle transient errors
- **Implementation**: Retry loop with delay
- **Formula**: `delay = base_delay * (2 ** attempt)`
- **Max Retries**: 3 attempts

### 3. Timeout Management
- **Purpose**: Prevent hanging requests
- **Implementation**: `asyncio.timeout()` context
- **Timeouts**:
  - API requests: 60s (configurable)
  - Claude calls: 300s (configurable)
  - MCP tool calls: 60s (configurable)

### 4. Resource Cleanup
- **Purpose**: Prevent resource leaks
- **Implementation**: `AsyncExitStack`
- **Resources**:
  - HTTP connections
  - MCP sessions
  - Subprocess handles

### 5. Graceful Degradation
- **Strategy**: Continue with partial data
- **Implementation**: Tool calls return errors, Claude adapts
- **Example**: If logs unavailable, analyze metrics only

---

## Security Architecture

### Authentication
- **Webhook**: Optional Bearer token
- **Cloud Providers**: Service accounts, IAM roles
- **Anthropic**: API key (environment variable)

### Authorization
- **Project-Level**: Per-project credentials
- **Tool-Level**: MCP tools scoped to project
- **Network-Level**: Private network deployment

### Secrets Management
- **Never in Code**: No hardcoded credentials
- **Environment Variables**: For API keys
- **Service Accounts**: JSON files outside repo
- **Secret Managers**: Support for cloud secret stores

### Audit Logging
- **All Requests**: Logged with correlation ID
- **Tool Calls**: Logged with parameters
- **Configuration Changes**: Logged with diff
- **Authentication**: Success/failure logged

---

## Performance Considerations

### Concurrency
- **Async I/O**: Non-blocking operations
- **Semaphores**: Bounded concurrency
- **Connection Pooling**: HTTP client reuse
- **Parallel Queries**: Concurrent metric fetches

### Caching (Future)
- **Configuration**: Cache parsed config
- **Tool Results**: Cache repeated queries
- **Prompt Templates**: Pre-compiled templates
- **Auth Tokens**: Cache until expiry

### Memory Management
- **Streaming**: Stream large log results
- **Pagination**: Limit log entries
- **Garbage Collection**: Explicit cleanup
- **Resource Limits**: Container memory limits

### Database (Future)
- **Historical RCA**: Store for pattern matching
- **Alert Correlation**: Time-series data
- **Analytics**: Aggregated metrics
- **Caching**: Redis for hot data

---

## Deployment Architecture

### Container Image
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "src/api/server.py"]
```

### Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-rca
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: mcp-rca
        image: mcp-rca:latest
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 2000m
            memory: 4Gi
        env:
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: anthropic
              key: api-key
```

### Production Recommendations
- **Replicas**: 3+ for HA
- **CPU**: 2 cores per replica
- **Memory**: 4GB per replica
- **Storage**: Ephemeral (stateless)
- **Load Balancer**: For webhook endpoint
- **Service Mesh**: For inter-service communication

---

## Monitoring & Observability

### Prometheus Metrics

#### Counters
- `rca_alerts_received_total{project, status}`
- `rca_api_requests_total{endpoint, method, status}`

#### Gauges
- `rca_alerts_processing{project}`

#### Histograms
- `rca_alert_processing_duration_seconds{project, status}`
- `rca_tool_calls_per_alert{project}`

### Log Aggregation
- **Format**: JSON for parsing
- **Destination**: stdout (captured by container runtime)
- **Correlation**: ID in every log line
- **Sampling**: All errors, sample info logs

### Alerting Rules (Prometheus)
```yaml
- alert: HighAlertProcessingTime
  expr: histogram_quantile(0.95, rca_alert_processing_duration_seconds) > 60
  for: 5m

- alert: CircuitBreakerOpen
  expr: rca_circuit_breaker_state{state="open"} > 0
  for: 1m
```

---

## Testing Strategy

### Unit Tests
- **Coverage Target**: 90%+
- **Framework**: pytest
- **Mocking**: unittest.mock, pytest-mock
- **Async**: pytest-asyncio

### Integration Tests
- **Cloud APIs**: Test against real APIs (sandbox)
- **MCP Protocol**: End-to-end MCP tests
- **Database**: Test with test database
- **Network**: Test with test endpoints

### Load Tests
- **Tool**: Locust, k6
- **Scenarios**:
  - 100 alerts/minute
  - 1000 alerts/minute (burst)
  - Sustained load for 1 hour
- **Metrics**: Latency, error rate, throughput

### Chaos Engineering
- **Network**: Latency injection, packet loss
- **API**: Random failures, timeouts
- **Resources**: CPU/memory limits
- **Tools**: Chaos Mesh, Litmus

---

## Future Architecture Enhancements

### Event-Driven Architecture
- **Message Queue**: RabbitMQ, Kafka
- **Event Sourcing**: Store all events
- **CQRS**: Separate read/write models

### Microservices Split
- **Alert Router**: Dedicated service
- **Analysis Engine**: Dedicated service
- **Notification Service**: Dedicated service
- **Analytics Service**: Dedicated service

### Data Layer
- **PostgreSQL**: Structured data (incidents, analysis)
- **TimescaleDB**: Time-series metrics
- **Elasticsearch**: Log search
- **Redis**: Caching, rate limiting

---

## Appendix

### Technology Choices

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Web Framework | Quart | Async-first, Flask-like API |
| HTTP Client | httpx | Async, HTTP/2 support |
| Config Validation | Pydantic | Type-safe, automatic validation |
| Logging | Python logging | Standard, extensible |
| Metrics | Prometheus | Industry standard |
| LLM | Claude 3.7 Sonnet | Best reasoning, tool use |
| Protocol | MCP | Standard for LLM tools |

### PEP 8 Compliance
- **Imports**: Sorted (stdlib, third-party, local)
- **Line Length**: 88 characters (Black default)
- **Naming**: snake_case, PascalCase, UPPER_CASE
- **Docstrings**: Google style
- **Type Hints**: Comprehensive

### Performance Benchmarks
- **Alert Processing**: 15s average, 30s p95
- **Tool Calls**: 2-5 per alert
- **API Latency**: 50ms p95
- **Memory**: 500MB per replica
- **CPU**: 0.5 cores average

---

**Document Version**: 1.0.0
**Last Updated**: 2026-01-08
**Maintained By**: Platform Engineering Team
