import time
from typing import Optional
from rate_limiter import RateLimiterBackend

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class RedisBackend(RateLimiterBackend):
    """Redis backend for rate limiting using sorted sets."""

    def __init__(self, redis_client: Optional['redis.Redis'] = None,
                 host: str = 'localhost', port: int = 6379, db: int = 0,
                 key_prefix: str = 'rate_limiter:'):
        """
        Initialize Redis backend.

        Args:
            redis_client: Existing Redis client instance
            host: Redis host (used if redis_client is None)
            port: Redis port (used if redis_client is None)
            db: Redis database number (used if redis_client is None)
            key_prefix: Prefix for all Redis keys
        """
        if not REDIS_AVAILABLE:
            raise ImportError("redis package is required for RedisBackend. Install with: pip install redis")

        if redis_client is not None:
            self.redis_client = redis_client
        else:
            self.redis_client = redis.Redis(host=host, port=port, db=db, decode_responses=False)

        self.key_prefix = key_prefix

    def _get_key(self, resource_key: str) -> str:
        """Get the Redis key for a resource."""
        return f"{self.key_prefix}{resource_key}"

    def add_request(self, resource_key: str, timestamp: float) -> None:
        """Add a request timestamp for a resource using Redis sorted sets."""
        key = self._get_key(resource_key)
        # Use timestamp as both score and member for uniqueness
        # Add a small random component to handle concurrent requests
        unique_timestamp = f"{timestamp}:{time.time_ns()}"
        self.redis_client.zadd(key, {unique_timestamp: timestamp})

    def get_request_count(self, resource_key: str, window_start: float) -> int:
        """Get the number of requests within the time window."""
        key = self._get_key(resource_key)
        # Count members with score >= window_start
        return self.redis_client.zcount(key, window_start, '+inf')

    def cleanup_old_requests(self, resource_key: str, window_start: float) -> None:
        """Remove requests older than the window start."""
        key = self._get_key(resource_key)
        # Remove all members with score < window_start
        self.redis_client.zremrangebyscore(key, '-inf', f"({window_start}")

    def get_oldest_request_time(self, resource_key: str, window_start: float) -> float:
        """Get the timestamp of the oldest request in the current window."""
        key = self._get_key(resource_key)
        # Get the first element (oldest) with score >= window_start
        result = self.redis_client.zrangebyscore(
            key, window_start, '+inf', start=0, num=1, withscores=True
        )

        if result:
            return float(result[0][1])  # Return the score (timestamp)

        return window_start

    def clear_resource(self, resource_key: str) -> None:
        """Clear all requests for a resource."""
        key = self._get_key(resource_key)
        self.redis_client.delete(key)