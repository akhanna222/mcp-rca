# Demo Applications

This directory contains demonstration applications for testing the MCP-RCA platform.

## Microservice API Demo

A production-quality microservice that simulates real-world scenarios for testing RCA capabilities.

### Features

- **RESTful API** endpoints (documents, file upload)
- **Prometheus metrics** for monitoring
- **Configurable error injection** for testing
- **Simulated slow requests** to trigger latency alerts
- **Database and storage operations** with failures
- **Chaos engineering endpoints** for load testing

### Running the Demo

```bash
# Install dependencies
pip install quart prometheus-client

# Run with default settings (10% error rate, 5% slow requests)
python demo/microservice_api.py

# Run with custom error injection
ERROR_INJECTION_RATE=0.2 SLOW_REQUEST_RATE=0.1 python demo/microservice_api.py

# Run on custom port
PORT=9000 python demo/microservice_api.py
```

### Available Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |
| `/api/documents` | POST | Create a document |
| `/api/documents` | GET | List all documents |
| `/api/upload` | POST | Upload a file |
| `/api/chaos/cpu-spike` | POST | Trigger CPU-intensive operation |
| `/api/chaos/memory-leak` | POST | Trigger memory allocation |

### Testing Scenarios

#### 1. Create Documents with Errors

```bash
# Normal request
curl -X POST http://localhost:8080/api/documents \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Document", "content": "Hello World"}'

# This will occasionally fail with 500 errors (configurable rate)
```

#### 2. Upload Files with Storage Failures

```bash
# Upload a file
curl -X POST http://localhost:8080/api/upload \
  -F "file=@test.txt"

# This may fail with "Storage unavailable" errors
```

#### 3. Trigger Performance Issues

```bash
# Trigger CPU spike
curl -X POST http://localhost:8080/api/chaos/cpu-spike

# Trigger memory leak
curl -X POST http://localhost:8080/api/chaos/memory-leak
```

#### 4. Monitor Metrics

```bash
# View Prometheus metrics
curl http://localhost:8080/metrics

# Key metrics:
# - demo_api_requests_total
# - demo_api_request_duration_seconds
# - demo_api_errors_total
# - demo_api_db_operations_total
# - demo_api_storage_operations_total
```

### Integrating with MCP-RCA

1. **Configure GCP Monitoring** to scrape metrics from the demo app

2. **Set up alerts** for:
   - High error rate: `demo_api_errors_total`
   - High latency: `demo_api_request_duration_seconds`
   - Database failures: `demo_api_db_operations_total{status="error"}`
   - Storage failures: `demo_api_storage_operations_total{status="error"}`

3. **Configure webhook** in GCP to send alerts to MCP-RCA platform

4. **Test RCA** by triggering errors and observing the automated analysis

### Example Alert Configuration (GCP)

```yaml
# Alert for high error rate
displayName: "High Error Rate"
conditions:
  - displayName: "Error rate > 10%"
    conditionThreshold:
      filter: 'metric.type="prometheus.googleapis.com/demo_api_errors_total/counter"'
      comparison: COMPARISON_GT
      thresholdValue: 10
      duration: 60s

notificationChannels:
  - projects/PROJECT_ID/notificationChannels/WEBHOOK_ID

documentation:
  content: "Error rate exceeded 10% threshold"
```

### Load Testing

Use `locust` or `k6` to generate load:

```python
# locustfile.py
from locust import HttpUser, task, between

class DemoAPIUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def create_document(self):
        self.client.post("/api/documents", json={
            "title": "Test",
            "content": "Content"
        })

    @task(1)
    def list_documents(self):
        self.client.get("/api/documents")
```

Run load test:
```bash
locust -f locustfile.py --host http://localhost:8080
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ERROR_INJECTION_RATE` | `0.1` | Probability of injecting errors (0.0-1.0) |
| `SLOW_REQUEST_RATE` | `0.05` | Probability of slow requests (0.0-1.0) |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8080` | Server port |

### Architecture

```
┌─────────────────────────────────────────┐
│         Demo Microservice API           │
│  ┌───────────────────────────────────┐  │
│  │  HTTP Endpoints (Quart)           │  │
│  └───────────────┬───────────────────┘  │
│                  │                       │
│  ┌───────────────▼───────────────────┐  │
│  │  Business Logic                   │  │
│  │  - Error Injection                │  │
│  │  - Latency Simulation             │  │
│  └───────┬──────────────┬────────────┘  │
│          │              │                │
│  ┌───────▼──────┐  ┌───▼────────────┐  │
│  │  Simulated   │  │  Simulated     │  │
│  │  Database    │  │  Storage       │  │
│  └──────────────┘  └────────────────┘  │
│                                          │
│  ┌───────────────────────────────────┐  │
│  │  Prometheus Metrics               │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
            │
            ▼
      GCP Monitoring
            │
            ▼
    Alert Triggered
            │
            ▼
     MCP-RCA Platform
```

## Future Demos

- **Kubernetes workload** with pod failures
- **Database migration** with transaction errors
- **Message queue** processing with backpressure
- **Distributed tracing** integration
