# Sliding Window Rate Limiter

A Python rate limiter implementation with sliding window algorithm supporting both in-memory and Redis backends. Includes HTTP API server for easy testing and load testing.

## Quick Start Guide

### 1. Bootstrap All Components

Start the complete stack (Redis + API server) with Docker Compose:

```bash
# Start all services
docker-compose up --build

# Or run in background
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

This starts:
- **Redis** on port 6379
- **API server** on port 5000 (Flask with rate limiting)

### 2. Make a Single Request

Test with a simple curl command:

```bash
# Basic request (5 req/sec limit)
curl "http://localhost:5000/api/user?user_id=alice"

# Response (success):
{
  "status": "success",
  "resource": "user",
  "user_id": "alice",
  "timestamp": 1234567890.123,
  "message": "Request processed successfully"
}
```

Check the rate limit status:

```bash
curl "http://localhost:5000/status/user?user_id=alice"

# Response shows configuration, current usage, and sleep time:
{
  "resource": "user",
  "user_id": "alice",
  "current_sleep_time": 0.0,
  "status": {
    "resource_name": "user_alice",
    "configuration": {
      "requests_per_second": 5,
      "requests_per_minute": 10
    },
    "current_usage": {
      "requests_per_second": {
        "current": 1,
        "limit": 5
      },
      "requests_per_minute": {
        "current": 1,
        "limit": 10
      }
    },
    "current_sleep_time_requests": 0.0
  }
}
```

### 3. Generate Load to Trigger Rate Limiting

Send rapid requests to hit the rate limit (5 req/sec):

```bash
# Send 10 rapid requests in parallel
for i in {1..10}; do
  curl -s "http://localhost:5000/api/user?user_id=bob" &
done
wait

# Check the results - some will succeed, some will be rate limited
for i in {1..10}; do
  curl -s "http://localhost:5000/api/user?user_id=bob" | jq -r '.status'
  sleep 0.1
done

# Expected output mix:
"success"
"success"
"success"
"success"
"success"
"rate_limited"  # <- Rate limiting kicks in
"rate_limited"
"rate_limited"
"rate_limited"
"rate_limited"
```

### 4. View Logs to Verify Rate Limiting

#### View Docker Container Logs

```bash
# Follow all logs
docker-compose logs -f

# Filter for rate limiting events
docker-compose logs -f | grep -i "rate"

# View only API server logs
docker-compose logs -f rate_limiter_app
```

#### View JSON Log Files

The logs directory contains structured logs:

```bash
# View structured JSON logs
cat logs/rate_limiter.jsonl | jq '.'

# Filter for rate limited requests
cat logs/rate_limiter.jsonl | jq 'select(.message | contains("RATE_LIMITED"))'

# View sleep times
cat logs/rate_limiter.jsonl | jq 'select(.sleep_time > 0) | {resource_key, sleep_time, request_count}'

# View performance metrics
tail -f logs/performance.log

# Check for errors
tail -f logs/errors.log
```

#### Example Log Output

When rate limited, you'll see logs showing which limit was hit:

```json
{
  "timestamp": "2025-01-21T10:30:45.123456",
  "level": "INFO",
  "logger": "rate_limiter.main",
  "message": "RATE_LIMITED: user_bob:rps (sleep: 0.185s) (count: 5)",
  "resource_key": "user_bob:rps",
  "sleep_time": 0.185,
  "request_count": 5,
  "limit_type": "requests_per_second",
  "max_requests": 5,
  "time_window": 1.0,
  "backend_type": "RedisBackend"
}
```

The `limit_type` field shows which limit was triggered (e.g., `requests_per_second`, `requests_per_minute`, `tokens_per_second`, `tokens_per_minute`).

---

## Advanced Usage

### API Endpoints

- **GET/POST `/api/<resource>`** - Main API endpoint with rate limiting
  - Query params: `user_id`, `work_time`
  - Default limits: 5 req/sec, 10 req/min

- **GET `/status/<resource>`** - Check rate limit status with current usage
  - Query params: `user_id`
  - Returns configuration, current usage counters, and sleep time

- **GET `/health`** - Health check endpoint

- **GET `/redis-info`** - Redis memory and key information

### Load Testing with curl

```bash
# Parallel requests to test thread safety
for i in {1..20}; do
  curl -s "http://localhost:5000/api/user?user_id=user_$i" &
done
wait

# Test with work simulation (0.1s per request)
curl "http://localhost:5000/api/user?user_id=test&work_time=0.1"

# Monitor current usage during load (launch requests in background and check status)
for i in {1..10}; do
  curl -s "http://localhost:5000/api/user?user_id=loadtest" > /dev/null &
done
sleep 0.2
curl "http://localhost:5000/status/user?user_id=loadtest" | jq '.status.current_usage'
# Shows: {"requests_per_second": {"current": 10, "limit": 5}, ...}

# Monitor Redis during load
curl "http://localhost:5000/redis-info" | jq '.key_details'
```

### Testing Scripts

Run the included test and demo scripts:

```bash
# Test rate limiting with sequential and parallel requests
source venv/bin/activate
python test_rate_limiting.py

# Demonstrate memory leak
./demo_memory_leak.sh

# Monitor Redis in real-time
./redis_monitor.sh
```

### Local Development (Without Docker)

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start Redis locally
redis-server

# Run API server
python api_server.py
```

---

## Configuration

### Rate Limit Configuration

The API uses default rate limits of **5 req/sec** and **10 req/min** for all endpoints.

To customize, edit [api_server.py](api_server.py):

```python
# In api_endpoint() function, around line 82
manager.configure_resource(resource_key, requests_per_second=5, requests_per_minute=10)
```

### Environment Variables

```bash
# Redis connection
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_DB=0

# Logging
export LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# API server
export API_PORT=5000
export FLASK_DEBUG=false
```

---

## Architecture

### Components

- **[rate_limiter.py](rate_limiter.py)** - Core sliding window algorithm
- **[rate_limiter_manager.py](rate_limiter_manager.py)** - Multi-resource management
- **[memory_backend.py](memory_backend.py)** - In-memory storage backend
- **[redis_backend.py](redis_backend.py)** - Redis storage backend
- **[api_server.py](api_server.py)** - Flask HTTP API server
- **[logger_config.py](logger_config.py)** - Structured logging configuration

### Sliding Window Algorithm

The rate limiter uses a precise sliding window algorithm:
1. Timestamps are stored in sorted sets (Redis) or sorted lists (memory)
2. Old timestamps outside the window are removed
3. Current count is checked against limits
4. Sleep time is calculated based on oldest timestamp in window

---

## Troubleshooting

### Check Service Health

```bash
# API health check
curl http://localhost:5000/health

# Redis connectivity
docker-compose exec redis redis-cli ping

# View container status
docker-compose ps
```

### Common Issues

**Redis Connection Failed**
```bash
# Check Redis logs
docker-compose logs redis

# Verify Redis is running
docker-compose ps redis
```

**API Not Responding**
```bash
# Check API logs
docker-compose logs rate_limiter_app

# Restart services
docker-compose restart
```

**Rate Limiter Not Working**
```bash
# Enable debug logging
docker-compose down
LOG_LEVEL=DEBUG docker-compose up

# Check configuration
curl http://localhost:5000/status/user?user_id=test
```

---

## Features

- **Sliding Window Algorithm**: Precise rate limiting with timestamps
- **Multiple Backends**: In-memory and Redis storage options
- **Resource Management**: Configure multiple resources with different rate limits
- **HTTP API**: Easy testing with curl and load testing tools
- **Thread-safe**: Safe for concurrent usage
- **Comprehensive Logging**: Structured JSON logging with performance metrics
- **Docker Support**: Ready-to-run Docker Compose setup