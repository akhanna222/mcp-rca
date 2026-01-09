#!/usr/bin/env python3
"""Professional microservice API demo for MCP-RCA platform.

This demo application simulates a production microservice with:
- RESTful API endpoints
- Database operations
- Cloud storage integration
- Monitoring instrumentation
- Error injection for testing RCA

Use this to generate realistic alerts for testing the RCA platform.
"""

import asyncio
import os
import random
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from quart import Quart, request, jsonify, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Prometheus metrics
REQUESTS_TOTAL = Counter(
    'demo_api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status']
)

REQUEST_DURATION = Histogram(
    'demo_api_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint']
)

ACTIVE_REQUESTS = Gauge(
    'demo_api_active_requests',
    'Currently active requests'
)

ERROR_RATE = Counter(
    'demo_api_errors_total',
    'Total errors',
    ['error_type']
)

DB_OPERATIONS = Counter(
    'demo_api_db_operations_total',
    'Total database operations',
    ['operation', 'status']
)

STORAGE_OPERATIONS = Counter(
    'demo_api_storage_operations_total',
    'Total storage operations',
    ['operation', 'status']
)

# Application setup
app = Quart(__name__)
app.config['ERROR_INJECTION_RATE'] = float(os.getenv('ERROR_INJECTION_RATE', '0.1'))
app.config['SLOW_REQUEST_RATE'] = float(os.getenv('SLOW_REQUEST_RATE', '0.05'))


class SimulatedDatabase:
    """Simulates database operations with configurable behavior."""

    def __init__(self):
        self.data: Dict[str, Dict[str, Any]] = {}
        self.connection_failures = 0

    async def insert(self, collection: str, document: Dict[str, Any]) -> str:
        """Insert a document into a collection.

        Args:
            collection: Collection name
            document: Document to insert

        Returns:
            Document ID

        Raises:
            ConnectionError: If database connection fails (simulated)
        """
        with REQUEST_DURATION.labels(method='DB', endpoint='insert').time():
            # Simulate occasional connection failures
            if random.random() < 0.02:  # 2% failure rate
                self.connection_failures += 1
                ERROR_RATE.labels(error_type='db_connection_failure').inc()
                DB_OPERATIONS.labels(operation='insert', status='error').inc()
                app.logger.error(
                    f"Database connection failed",
                    extra={
                        "collection": collection,
                        "failures_count": self.connection_failures
                    }
                )
                raise ConnectionError("Database connection failed")

            # Simulate slow queries
            if random.random() < 0.1:  # 10% slow queries
                await asyncio.sleep(random.uniform(1.0, 3.0))

            doc_id = str(uuid.uuid4())
            if collection not in self.data:
                self.data[collection] = {}

            self.data[collection][doc_id] = {
                **document,
                'id': doc_id,
                'created_at': datetime.utcnow().isoformat()
            }

            DB_OPERATIONS.labels(operation='insert', status='success').inc()
            return doc_id

    async def query(self, collection: str, filters: Optional[Dict[str, Any]] = None) -> list:
        """Query documents from a collection.

        Args:
            collection: Collection name
            filters: Query filters

        Returns:
            List of matching documents
        """
        with REQUEST_DURATION.labels(method='DB', endpoint='query').time():
            if collection not in self.data:
                DB_OPERATIONS.labels(operation='query', status='success').inc()
                return []

            # Simulate slow queries for large datasets
            if len(self.data[collection]) > 100:
                await asyncio.sleep(random.uniform(0.5, 1.5))

            results = list(self.data[collection].values())
            DB_OPERATIONS.labels(operation='query', status='success').inc()
            return results


class SimulatedStorage:
    """Simulates cloud storage operations."""

    def __init__(self):
        self.files: Dict[str, bytes] = {}
        self.upload_failures = 0

    async def upload(self, filename: str, content: bytes) -> str:
        """Upload a file to storage.

        Args:
            filename: Name of the file
            content: File content

        Returns:
            File URL

        Raises:
            RuntimeError: If upload fails (simulated)
        """
        with REQUEST_DURATION.labels(method='STORAGE', endpoint='upload').time():
            # Simulate occasional upload failures
            if random.random() < 0.05:  # 5% failure rate
                self.upload_failures += 1
                ERROR_RATE.labels(error_type='storage_upload_failure').inc()
                STORAGE_OPERATIONS.labels(operation='upload', status='error').inc()
                app.logger.error(
                    f"Storage upload failed",
                    extra={
                        "filename": filename,
                        "size_bytes": len(content),
                        "failures_count": self.upload_failures
                    }
                )
                raise RuntimeError("Storage upload failed")

            # Simulate upload time based on file size
            size_mb = len(content) / (1024 * 1024)
            await asyncio.sleep(size_mb * 0.1)  # 100ms per MB

            file_id = str(uuid.uuid4())
            self.files[file_id] = content

            STORAGE_OPERATIONS.labels(operation='upload', status='success').inc()
            return f"storage://{file_id}/{filename}"


# Initialize simulated backends
database = SimulatedDatabase()
storage = SimulatedStorage()


@app.before_request
async def before_request():
    """Track request start time and active requests."""
    ACTIVE_REQUESTS.inc()
    request.start_time = time.time()


@app.after_request
async def after_request(response: Response) -> Response:
    """Record metrics after request completion."""
    ACTIVE_REQUESTS.dec()

    duration = time.time() - request.start_time
    endpoint = request.endpoint or 'unknown'
    method = request.method

    REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)
    REQUESTS_TOTAL.labels(
        method=method,
        endpoint=endpoint,
        status=response.status_code
    ).inc()

    return response


@app.route('/health', methods=['GET'])
async def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0'
    }), 200


@app.route('/metrics', methods=['GET'])
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.route('/api/documents', methods=['POST'])
async def create_document():
    """Create a new document.

    Request Body:
        {
            "title": "Document title",
            "content": "Document content",
            "tags": ["tag1", "tag2"]
        }

    Returns:
        201: Document created
        400: Invalid request
        500: Server error
    """
    try:
        # Simulate slow requests
        if random.random() < app.config['SLOW_REQUEST_RATE']:
            app.logger.warning("Slow request detected", extra={
                "endpoint": "/api/documents",
                "method": "POST"
            })
            await asyncio.sleep(random.uniform(5.0, 10.0))

        # Simulate errors
        if random.random() < app.config['ERROR_INJECTION_RATE']:
            ERROR_RATE.labels(error_type='internal_server_error').inc()
            app.logger.error(
                "Simulated server error",
                extra={"endpoint": "/api/documents"}
            )
            return jsonify({'error': 'Internal server error'}), 500

        data = await request.get_json()

        # Validation
        if not data or 'title' not in data:
            return jsonify({'error': 'Title is required'}), 400

        # Insert into database
        doc_id = await database.insert('documents', {
            'title': data.get('title'),
            'content': data.get('content', ''),
            'tags': data.get('tags', [])
        })

        app.logger.info(
            "Document created",
            extra={"document_id": doc_id, "title": data.get('title')}
        )

        return jsonify({
            'id': doc_id,
            'message': 'Document created successfully'
        }), 201

    except ConnectionError as e:
        return jsonify({'error': 'Database unavailable'}), 503
    except Exception as e:
        ERROR_RATE.labels(error_type='unexpected_error').inc()
        app.logger.error(f"Unexpected error: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/documents', methods=['GET'])
async def list_documents():
    """List all documents.

    Returns:
        200: List of documents
        500: Server error
    """
    try:
        documents = await database.query('documents')

        return jsonify({
            'documents': documents,
            'count': len(documents)
        }), 200

    except Exception as e:
        ERROR_RATE.labels(error_type='unexpected_error').inc()
        app.logger.error(f"Failed to list documents: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/upload', methods=['POST'])
async def upload_file():
    """Upload a file.

    Request: multipart/form-data with 'file' field

    Returns:
        200: File uploaded
        400: Invalid request
        500: Server error
    """
    try:
        # Simulate slow requests
        if random.random() < app.config['SLOW_REQUEST_RATE']:
            await asyncio.sleep(random.uniform(5.0, 10.0))

        files = await request.files
        if 'file' not in files:
            return jsonify({'error': 'No file provided'}), 400

        file = files['file']
        if not file.filename:
            return jsonify({'error': 'Empty filename'}), 400

        # Read file content
        content = await file.read()

        # Upload to storage
        file_url = await storage.upload(file.filename, content)

        # Store metadata in database
        doc_id = await database.insert('files', {
            'filename': file.filename,
            'size_bytes': len(content),
            'url': file_url
        })

        app.logger.info(
            "File uploaded",
            extra={
                "file_id": doc_id,
                "filename": file.filename,
                "size_bytes": len(content)
            }
        )

        return jsonify({
            'id': doc_id,
            'url': file_url,
            'message': 'File uploaded successfully'
        }), 200

    except RuntimeError as e:
        return jsonify({'error': 'Storage unavailable'}), 503
    except ConnectionError as e:
        return jsonify({'error': 'Database unavailable'}), 503
    except Exception as e:
        ERROR_RATE.labels(error_type='unexpected_error').inc()
        app.logger.error(f"Upload failed: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/chaos/cpu-spike', methods=['POST'])
async def trigger_cpu_spike():
    """Trigger CPU-intensive operation (for testing).

    Returns:
        200: CPU spike triggered
    """
    app.logger.warning("CPU spike triggered")

    # Simulate CPU-intensive work
    result = 0
    for i in range(10_000_000):
        result += i * i

    return jsonify({
        'message': 'CPU spike completed',
        'result': result
    }), 200


@app.route('/api/chaos/memory-leak', methods=['POST'])
async def trigger_memory_leak():
    """Trigger memory leak (for testing).

    Returns:
        200: Memory leak triggered
    """
    app.logger.warning("Memory leak triggered")

    # Allocate large amount of memory
    leak = ['x' * 1024 * 1024 for _ in range(100)]  # 100MB

    return jsonify({
        'message': 'Memory allocated',
        'size_mb': 100
    }), 200


def main():
    """Run the demo application."""
    import asyncio
    import logging

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Run application
    port = int(os.getenv('PORT', '8080'))
    host = os.getenv('HOST', '0.0.0.0')

    print(f"Starting Demo API on {host}:{port}")
    print(f"Error injection rate: {app.config['ERROR_INJECTION_RATE'] * 100}%")
    print(f"Slow request rate: {app.config['SLOW_REQUEST_RATE'] * 100}%")
    print("\nEndpoints:")
    print("  POST /api/documents - Create document")
    print("  GET  /api/documents - List documents")
    print("  POST /api/upload - Upload file")
    print("  POST /api/chaos/cpu-spike - Trigger CPU spike")
    print("  POST /api/chaos/memory-leak - Trigger memory leak")
    print("  GET  /health - Health check")
    print("  GET  /metrics - Prometheus metrics")

    app.run(host=host, port=port, debug=False)


if __name__ == '__main__':
    main()
