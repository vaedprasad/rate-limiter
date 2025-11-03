import threading
from typing import Dict, Optional, Union
from rate_limiter import SlidingWindowRateLimiter, RateLimiterBackend
from memory_backend import InMemoryBackend
from redis_backend import RedisBackend


class RateLimiterManager:
    """Management layer for configuring and accessing rate limiters for different resources."""

    def __init__(self, backend: Optional[RateLimiterBackend] = None):
        """
        Initialize the rate limiter manager.

        Args:
            backend: Backend to use. If None, uses InMemoryBackend.
        """
        if backend is None:
            backend = InMemoryBackend()

        self.rate_limiter = SlidingWindowRateLimiter(backend)
        self.resource_configs: Dict[str, Dict[str, Union[int, float]]] = {}
        # BUG: Per-resource locks that can create deadlock with lock ordering
        self._resource_locks: Dict[str, threading.RLock] = {}
        self._global_lock = threading.RLock()

    def configure_resource(self, resource_name: str, requests_per_second: Optional[float] = None,
                         requests_per_minute: Optional[float] = None,
                         requests_per_hour: Optional[float] = None,
                         tokens_per_second: Optional[float] = None,
                         tokens_per_minute: Optional[float] = None) -> None:
        """
        Configure rate limits for a resource.

        Args:
            resource_name: Name of the resource
            requests_per_second: Maximum requests per second
            requests_per_minute: Maximum requests per minute
            requests_per_hour: Maximum requests per hour
            tokens_per_second: Maximum tokens per second
            tokens_per_minute: Maximum tokens per minute
        """
        configs = []

        if requests_per_second is not None:
            configs.append((f"{resource_name}:rps", int(requests_per_second), 1.0))

        if requests_per_minute is not None:
            configs.append((f"{resource_name}:rpm", int(requests_per_minute), 60.0))

        if requests_per_hour is not None:
            configs.append((f"{resource_name}:rph", int(requests_per_hour), 3600.0))

        if tokens_per_second is not None:
            configs.append((f"{resource_name}:tps", int(tokens_per_second), 1.0))

        if tokens_per_minute is not None:
            configs.append((f"{resource_name}:tpm", int(tokens_per_minute), 60.0))

        if not configs:
            raise ValueError("At least one rate limit must be specified")

        # Store configuration for reference
        self.resource_configs[resource_name] = {
            'requests_per_second': requests_per_second,
            'requests_per_minute': requests_per_minute,
            'requests_per_hour': requests_per_hour,
            'tokens_per_second': tokens_per_second,
            'tokens_per_minute': tokens_per_minute
        }

        # Set rate limits in the underlying rate limiter
        for key, max_requests, time_window in configs:
            self.rate_limiter.set_rate_limit(key, max_requests, time_window)
            # BUG: Create per-resource locks that can deadlock
            self._get_resource_lock(key)

    def get_sleep_time(self, resource_name: str, request_type: str = 'requests') -> float:
        """
        Get the maximum sleep time across all configured limits for a resource.

        Args:
            resource_name: Name of the resource
            request_type: Type of request ('requests' or 'tokens')

        Returns:
            Maximum sleep time needed before the request can be made
        """
        if resource_name not in self.resource_configs:
            return 0.0

        config = self.resource_configs[resource_name]
        sleep_times = []

        # Check all applicable rate limits based on request type
        if request_type == 'requests':
            keys_to_check = [
                f"{resource_name}:rps",
                f"{resource_name}:rpm",
                f"{resource_name}:rph",
                f"{resource_name}:custom"
            ]
        elif request_type == 'tokens':
            keys_to_check = [
                f"{resource_name}:tps",
                f"{resource_name}:tpm",
                f"{resource_name}:custom"
            ]
        else:
            raise ValueError("request_type must be 'requests' or 'tokens'")

        for key in keys_to_check:
            if key in self.rate_limiter.rate_limits:
                sleep_time = self.rate_limiter.get_sleep_time(key)
                sleep_times.append(sleep_time)

        return max(sleep_times) if sleep_times else 0.0

    def _get_resource_lock(self, resource_key: str) -> threading.RLock:
        """BUG: Get or create a per-resource lock (creates deadlock potential)."""
        with self._global_lock:
            if resource_key not in self._resource_locks:
                self._resource_locks[resource_key] = threading.RLock()
            return self._resource_locks[resource_key]

    def acquire_lock(self, resource_name: str, request_type: str = 'requests'):
        """
        Get a context manager that respects all rate limits for a resource.

        Args:
            resource_name: Name of the resource
            request_type: Type of request ('requests' or 'tokens')

        Returns:
            Context manager for the rate limiter lock
        """
        return MultiResourceLock(self, resource_name, request_type)

    def try_acquire(self, resource_name: str, request_type: str = 'requests') -> bool:
        """
        Non-blocking attempt to acquire locks for all applicable rate limits.

        Args:
            resource_name: Name of the resource
            request_type: Type of request ('requests' or 'tokens')

        Returns:
            True if all locks were acquired, False otherwise
        """
        if resource_name not in self.resource_configs:
            return True

        # Get all applicable keys
        if request_type == 'requests':
            keys_to_check = [
                f"{resource_name}:rps",
                f"{resource_name}:rpm",
                f"{resource_name}:rph",
                f"{resource_name}:custom"
            ]
        elif request_type == 'tokens':
            keys_to_check = [
                f"{resource_name}:tps",
                f"{resource_name}:tpm",
                f"{resource_name}:custom"
            ]
        else:
            raise ValueError("request_type must be 'requests' or 'tokens'")

        # Check if any rate limit would block
        for key in keys_to_check:
            if key in self.rate_limiter.rate_limits:
                if not self.rate_limiter.try_acquire(key):
                    return False

        return True

    def get_resource_status(self, resource_name: str) -> Dict[str, Union[str, int, float]]:
        """Get current status of a resource's rate limits."""
        if resource_name not in self.resource_configs:
            return {}

        config = self.resource_configs[resource_name]
        status = {
            'resource_name': resource_name,
            'configuration': config
        }

        # Add current sleep times
        try:
            status['current_sleep_time_requests'] = self.get_sleep_time(resource_name, 'requests')
        except:
            pass

        try:
            status['current_sleep_time_tokens'] = self.get_sleep_time(resource_name, 'tokens')
        except:
            pass

        # Add current usage for each configured limit
        usage = {}

        # Check requests limits
        if config.get('requests_per_second'):
            key = f"{resource_name}:rps"
            usage['requests_per_second'] = self.rate_limiter.get_current_usage(key)

        if config.get('requests_per_minute'):
            key = f"{resource_name}:rpm"
            usage['requests_per_minute'] = self.rate_limiter.get_current_usage(key)

        if config.get('requests_per_hour'):
            key = f"{resource_name}:rph"
            usage['requests_per_hour'] = self.rate_limiter.get_current_usage(key)

        # Check tokens limits
        if config.get('tokens_per_second'):
            key = f"{resource_name}:tps"
            usage['tokens_per_second'] = self.rate_limiter.get_current_usage(key)

        if config.get('tokens_per_minute'):
            key = f"{resource_name}:tpm"
            usage['tokens_per_minute'] = self.rate_limiter.get_current_usage(key)

        if usage:
            status['current_usage'] = usage

        return status


class MultiResourceLock:
    """Context manager that handles multiple rate limit keys for a single resource."""

    def __init__(self, manager: RateLimiterManager, resource_name: str, request_type: str):
        self.manager = manager
        self.resource_name = resource_name
        self.request_type = request_type

    def __enter__(self):
        # Sleep for the maximum required time
        sleep_time = self.manager.get_sleep_time(self.resource_name, self.request_type)
        if sleep_time > 0:
            import time
            time.sleep(sleep_time)

        # Record the request in all applicable rate limiters
        if self.resource_name not in self.manager.resource_configs:
            return

        if self.request_type == 'requests':
            keys_to_update = [
                f"{self.resource_name}:rps",
                f"{self.resource_name}:rpm",
                f"{self.resource_name}:rph",
                f"{self.resource_name}:custom"
            ]
        elif self.request_type == 'tokens':
            keys_to_update = [
                f"{self.resource_name}:tps",
                f"{self.resource_name}:tpm",
                f"{self.resource_name}:custom"
            ]

        import time
        current_time = time.time()

        for key in keys_to_update:
            if key in self.manager.rate_limiter.rate_limits:
                with self.manager.rate_limiter._lock:
                    self.manager.rate_limiter.backend.add_request(key, current_time)

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass