import time
import threading
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional
from dataclasses import dataclass
from contextlib import contextmanager
from logger_config import log_rate_limit_event, log_performance_metrics


@dataclass
class RateLimit:
    """Configuration for a rate limit."""
    max_requests: int
    time_window: float  # in seconds


class RateLimiterBackend(ABC):
    """Abstract base class for rate limiter backends."""

    @abstractmethod
    def add_request(self, resource_key: str, timestamp: float) -> None:
        """Add a request timestamp for a resource."""
        pass

    @abstractmethod
    def get_request_count(self, resource_key: str, window_start: float) -> int:
        """Get the number of requests within the time window."""
        pass

    @abstractmethod
    def cleanup_old_requests(self, resource_key: str, window_start: float) -> None:
        """Remove requests older than the window start."""
        pass


class SlidingWindowRateLimiter:
    """Sliding window rate limiter with pluggable backends."""

    def __init__(self, backend: RateLimiterBackend):
        self.backend = backend
        self.rate_limits: Dict[str, RateLimit] = {}
        self._lock = threading.RLock()
        self.logger = logging.getLogger('rate_limiter.main')

    def set_rate_limit(self, resource_key: str, max_requests: int, time_window: float) -> None:
        """Configure rate limit for a resource."""
        with self._lock:
            self.rate_limits[resource_key] = RateLimit(max_requests, time_window)
            log_rate_limit_event(
                self.logger, 'config_updated', resource_key,
                backend_type=self.backend.__class__.__name__,
                rate_limit_config={'max_requests': max_requests, 'time_window': time_window}
            )

    def get_sleep_time(self, resource_key: str) -> float:
        """
        Non-blocking call that returns how long to sleep before the request can be made.
        Returns 0 if the request can be made immediately.
        """
        start_time = time.time()

        if resource_key not in self.rate_limits:
            return 0.0

        rate_limit = self.rate_limits[resource_key]
        current_time = time.time()
        window_start = current_time - rate_limit.time_window

        with self._lock:
            current_count = self.backend.get_request_count(resource_key, window_start)

            if current_count < rate_limit.max_requests:
                self.backend.cleanup_old_requests(resource_key, window_start)

                log_rate_limit_event(
                    self.logger, 'request_allowed', resource_key,
                    sleep_time=0.0, request_count=current_count,
                    backend_type=self.backend.__class__.__name__
                )
                return 0.0

            # Calculate when the oldest request in the window will expire
            if hasattr(self.backend, 'get_oldest_request_time'):
                oldest_time = self.backend.get_oldest_request_time(resource_key, window_start)
                sleep_until = oldest_time + rate_limit.time_window
                sleep_time = max(0.0, sleep_until - current_time)
            else:
                # Fallback to conservative estimate
                sleep_time = rate_limit.time_window

            # Extract limit type from resource key (e.g., "user:rps" -> "requests_per_second")
            limit_type_map = {
                'rps': 'requests_per_second',
                'rpm': 'requests_per_minute',
                'rph': 'requests_per_hour',
                'tps': 'tokens_per_second',
                'tpm': 'tokens_per_minute'
            }
            limit_type = None
            if ':' in resource_key:
                key_suffix = resource_key.split(':')[-1]
                limit_type = limit_type_map.get(key_suffix, key_suffix)

            log_rate_limit_event(
                self.logger, 'rate_limited', resource_key,
                sleep_time=sleep_time, request_count=current_count,
                backend_type=self.backend.__class__.__name__,
                limit_type=limit_type,
                max_requests=rate_limit.max_requests,
                time_window=rate_limit.time_window
            )

            # Log performance
            operation_time = time.time() - start_time
            perf_logger = logging.getLogger('rate_limiter.performance')
            log_performance_metrics(perf_logger, 'get_sleep_time', operation_time, resource_key)

            return sleep_time

    @contextmanager
    def acquire_lock(self, resource_key: str):
        """
        Context manager that acquires a rate limiter lock.
        Blocks until the request can be made according to rate limits.
        """
        sleep_time = self.get_sleep_time(resource_key)
        if sleep_time > 0:
            time.sleep(sleep_time)

        if resource_key in self.rate_limits:
            with self._lock:
                self.backend.add_request(resource_key, time.time())

        yield

    def try_acquire(self, resource_key: str) -> bool:
        """
        Non-blocking attempt to acquire the rate limiter lock.
        Returns True if successful, False if rate limited.
        """
        sleep_time = self.get_sleep_time(resource_key)
        if sleep_time > 0:
            return False

        if resource_key in self.rate_limits:
            with self._lock:
                self.backend.add_request(resource_key, time.time())

        return True

    def get_current_usage(self, resource_key: str) -> Dict[str, int]:
        """
        Get the current usage count for a resource.

        Args:
            resource_key: The resource key to check

        Returns:
            Dictionary with current count and max limit
        """
        if resource_key not in self.rate_limits:
            return {'current': 0, 'limit': 0}

        rate_limit = self.rate_limits[resource_key]
        current_time = time.time()
        window_start = current_time - rate_limit.time_window

        with self._lock:
            current_count = self.backend.get_request_count(resource_key, window_start)
            return {
                'current': current_count,
                'limit': rate_limit.max_requests
            }