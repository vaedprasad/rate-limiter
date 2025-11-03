#!/usr/bin/env python3
"""
HTTP API server for load testing the rate limiter bugs.
"""

import os
import time
import json
import threading
from flask import Flask, request, jsonify
from logger_config import setup_logging
from rate_limiter_manager import RateLimiterManager
from memory_backend import InMemoryBackend

try:
    from redis_backend import RedisBackend
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

app = Flask(__name__)

# Global rate limiter manager
manager = None
loggers = None


def initialize_rate_limiter():
    """Initialize the rate limiter with Redis or memory backend."""
    global manager, loggers

    loggers = setup_logging("INFO")
    main_logger = loggers['main']

    # Try Redis first, fallback to memory
    if REDIS_AVAILABLE:
        try:
            redis_config = {
                'host': os.getenv('REDIS_HOST', 'localhost'),
                'port': int(os.getenv('REDIS_PORT', 6379)),
                'db': int(os.getenv('REDIS_DB', 0))
            }

            # Test Redis connection
            client = redis.Redis(**redis_config, socket_connect_timeout=1)
            client.ping()

            backend = RedisBackend(**redis_config)
            main_logger.info(f"Using Redis backend: {redis_config['host']}:{redis_config['port']}")

        except Exception as e:
            main_logger.warning(f"Redis connection failed: {e}, using memory backend")
            backend = InMemoryBackend()
    else:
        main_logger.info("Redis not available, using memory backend")
        backend = InMemoryBackend()

    manager = RateLimiterManager(backend)

    # Configure default rate limits (only used for pre-configured resources)
    # Most resources are configured dynamically on first use

    main_logger.info("Rate limiter initialized with default configurations")


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "timestamp": time.time()})


@app.route('/api/<resource_name>', methods=['GET', 'POST'])
def api_endpoint(resource_name):
    """Main API endpoint that demonstrates rate limiting."""
    user_id = request.args.get('user_id', 'default_user')
    resource_key = f"{resource_name}_{user_id}"

    # Get or configure the resource
    if resource_key not in manager.resource_configs:
        # Configure with default limits: 5 req/sec, 10 req/min
        manager.configure_resource(resource_key, requests_per_second=5, requests_per_minute=10)

    try:
        # Check rate limit
        sleep_time = manager.get_sleep_time(resource_key, "requests")

        if sleep_time > 0:
            return jsonify({
                "status": "rate_limited",
                "resource": resource_name,
                "user_id": user_id,
                "sleep_time": sleep_time,
                "message": f"Rate limited. Try again in {sleep_time:.2f} seconds"
            }), 429

        # Acquire rate limit lock and process request
        with manager.acquire_lock(resource_key, "requests"):
            # Simulate some work
            work_time = request.args.get('work_time', '0.01')
            time.sleep(float(work_time))

            return jsonify({
                "status": "success",
                "resource": resource_name,
                "user_id": user_id,
                "timestamp": time.time(),
                "message": "Request processed successfully"
            })

    except Exception as e:
        loggers['main'].error(f"Error processing request: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route('/status/<resource_name>', methods=['GET'])
def status_endpoint(resource_name):
    """Get status of a resource's rate limits."""
    user_id = request.args.get('user_id', 'default_user')
    resource_key = f"{resource_name}_{user_id}"

    if resource_key in manager.resource_configs:
        status = manager.get_resource_status(resource_key)
        sleep_time = manager.get_sleep_time(resource_key, "requests")

        return jsonify({
            "resource": resource_name,
            "user_id": user_id,
            "status": status,
            "current_sleep_time": sleep_time
        })
    else:
        return jsonify({
            "resource": resource_name,
            "user_id": user_id,
            "message": "Resource not configured"
        }), 404


@app.route('/redis-info', methods=['GET'])
def redis_info():
    """Get Redis information for debugging."""
    if not REDIS_AVAILABLE:
        return jsonify({"error": "Redis not available"}), 503

    try:
        redis_config = {
            'host': os.getenv('REDIS_HOST', 'localhost'),
            'port': int(os.getenv('REDIS_PORT', 6379)),
            'db': int(os.getenv('REDIS_DB', 0))
        }

        client = redis.Redis(**redis_config)

        # Get all rate limiter keys
        keys = client.keys("rate_limiter:*")
        key_info = {}

        for key in keys:
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key

            # Get key info
            key_type = client.type(key).decode('utf-8')

            if key_type == 'zset':
                # Get sorted set info
                zcard = client.zcard(key)

                # Get oldest and newest entries
                oldest = client.zrange(key, 0, 0, withscores=True)
                newest = client.zrange(key, -1, -1, withscores=True)

                # Get memory usage if available
                try:
                    memory_usage = client.memory_usage(key)
                except:
                    memory_usage = None

                key_info[key_str] = {
                    'type': key_type,
                    'count': zcard,
                    'oldest_timestamp': oldest[0][1] if oldest else None,
                    'newest_timestamp': newest[0][1] if newest else None,
                    'memory_usage_bytes': memory_usage
                }
            else:
                key_info[key_str] = {
                    'type': key_type,
                    'count': 'N/A'
                }

        # Get Redis memory info
        memory_info = client.info('memory')

        return jsonify({
            "redis_config": redis_config,
            "total_keys": len(keys),
            "key_details": key_info,
            "memory_info": {
                "used_memory": memory_info.get('used_memory'),
                "used_memory_human": memory_info.get('used_memory_human'),
                "used_memory_peak": memory_info.get('used_memory_peak'),
                "used_memory_peak_human": memory_info.get('used_memory_peak_human')
            }
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/simulate-idle/<resource_name>', methods=['POST'])
def simulate_idle(resource_name):
    """Simulate a burst of requests followed by idle period (triggers the bug)."""
    user_id = request.args.get('user_id', f'idle_user_{int(time.time())}')
    resource_key = f"{resource_name}_{user_id}"

    # Configure very restrictive rate limit
    manager.configure_resource(resource_key, requests_per_second=1)

    burst_size = int(request.args.get('burst_size', '10'))

    # Make burst of requests (most will be rate limited)
    results = []
    for i in range(burst_size):
        sleep_time = manager.get_sleep_time(resource_key, "requests")

        if sleep_time > 0:
            results.append({
                "request": i + 1,
                "status": "rate_limited",
                "sleep_time": sleep_time
            })
        else:
            with manager.acquire_lock(resource_key, "requests"):
                results.append({
                    "request": i + 1,
                    "status": "success"
                })

    # Now this user is idle - old entries won't be cleaned up!
    return jsonify({
        "resource": resource_name,
        "user_id": user_id,
        "burst_results": results,
        "message": f"User {user_id} is now idle. Old entries will accumulate due to cleanup bug!"
    })


if __name__ == '__main__':
    initialize_rate_limiter()

    port = int(os.getenv('API_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'

    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)