# Claude Assistant Guide

This file contains essential information for AI assistants working on this project.

## Quick Reference

### System Commands

For all bootstrapping, testing, and operational commands, refer to [README.md](README.md).

Key sections:
- **Bootstrap**: [README.md#1-bootstrap-all-components](README.md#1-bootstrap-all-components)
- **Testing**: [README.md#2-make-a-single-request](README.md#2-make-a-single-request)
- **Load Testing**: [README.md#3-generate-load-to-trigger-rate-limiting](README.md#3-generate-load-to-trigger-rate-limiting)
- **Logs**: [README.md#4-view-logs-to-verify-rate-limiting](README.md#4-view-logs-to-verify-rate-limiting)

### Log Files Location

All logs are in the `logs/` directory:
- **`logs/rate_limiter.jsonl`** - Main structured JSON logs (overwrites on restart)
- **`logs/performance.log`** - Performance metrics
- **`logs/errors.log`** - Error logs with stack traces

The logs **overwrite on each restart** - no appending.

### Architecture Overview

**Core Components:**
- [rate_limiter.py](rate_limiter.py) - Sliding window algorithm implementation
- [rate_limiter_manager.py](rate_limiter_manager.py) - Multi-resource rate limit management
- [api_server.py](api_server.py) - Flask HTTP API for testing
- [memory_backend.py](memory_backend.py) - In-memory storage
- [redis_backend.py](redis_backend.py) - Redis storage
- [logger_config.py](logger_config.py) - Structured logging setup

**Current Configuration:**
- Rate limits: **5 req/sec, 10 req/min** (default for all endpoints)
- Supported limit types: `requests_per_second`, `requests_per_minute`, `requests_per_hour`, `tokens_per_second`, `tokens_per_minute`
- **No custom limits** - removed for simplicity

### Important Docker Commands

```bash
# Rebuild and restart (required after code changes)
docker-compose down && docker-compose up -d --build

# View logs
docker-compose logs -f rate_limiter_app

# Restart without rebuild (config changes only)
docker-compose restart rate_limiter_app

# Stop everything
docker-compose down
```

### API Endpoints

- `GET/POST /api/<resource>?user_id=<id>` - Main rate-limited endpoint
- `GET /status/<resource>?user_id=<id>` - Check rate limit status with current usage
- `GET /health` - Health check
- `GET /redis-info` - Redis debug information

### Key Features in Logs

Rate-limited events include:
```json
{
  "message": "RATE_LIMITED: user_bob:rpm (sleep: 5.79s) (count: 10)",
  "limit_type": "requests_per_minute",
  "max_requests": 10,
  "time_window": 60.0,
  "sleep_time": 5.797,
  "request_count": 10,
  "backend_type": "RedisBackend"
}
```

The `limit_type` field shows exactly which limit was hit.

### API Response Structure

Status endpoint returns:
```json
{
  "status": {
    "configuration": {
      "requests_per_second": 5,
      "requests_per_minute": 10
    },
    "current_usage": {
      "requests_per_second": {"current": 3, "limit": 5},
      "requests_per_minute": {"current": 8, "limit": 10}
    }
  }
}
```

### Testing Flow

1. Start services: `docker-compose up -d --build`
2. Make requests: `curl "http://localhost:5000/api/user?user_id=test"`
3. Check status: `curl "http://localhost:5000/status/user?user_id=test" | jq`
4. View logs: `cat logs/rate_limiter.jsonl | jq`
5. Trigger rate limit: Run 12+ requests rapidly
6. Verify logs show `RATE_LIMITED` events with `limit_type` field

### Important Notes

- **Always rebuild Docker** after code changes: `docker-compose down && docker-compose up -d --build`
- Logs overwrite on restart - old logs are lost
- Sequential curl requests may be too slow to trigger rate limits - use rapid parallel requests
- The `/min` limit (10 req/min) is easier to test than `/sec` limit
