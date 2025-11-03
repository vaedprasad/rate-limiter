import bisect
import threading
from typing import Dict, List
from rate_limiter import RateLimiterBackend


class InMemoryBackend(RateLimiterBackend):
    """In-memory backend for rate limiting using sorted lists of timestamps."""

    def __init__(self):
        self._requests: Dict[str, List[float]] = {}
        self._lock = threading.RLock()

    def add_request(self, resource_key: str, timestamp: float) -> None:
        """Add a request timestamp for a resource."""
        with self._lock:
            if resource_key not in self._requests:
                self._requests[resource_key] = []

            # Insert timestamp in sorted order
            bisect.insort(self._requests[resource_key], timestamp)

    def get_request_count(self, resource_key: str, window_start: float) -> int:
        """Get the number of requests within the time window."""
        with self._lock:
            if resource_key not in self._requests:
                return 0

            timestamps = self._requests[resource_key]
            # Find the index of the first timestamp >= window_start
            start_index = bisect.bisect_left(timestamps, window_start)
            return len(timestamps) - start_index

    def cleanup_old_requests(self, resource_key: str, window_start: float) -> None:
        """Remove requests older than the window start."""
        with self._lock:
            if resource_key not in self._requests:
                return

            timestamps = self._requests[resource_key]
            # Find the index of the first timestamp >= window_start
            start_index = bisect.bisect_left(timestamps, window_start)

            # Keep only timestamps from start_index onwards
            if start_index > 0:
                self._requests[resource_key] = timestamps[start_index:]

    def get_oldest_request_time(self, resource_key: str, window_start: float) -> float:
        """Get the timestamp of the oldest request in the current window."""
        with self._lock:
            if resource_key not in self._requests:
                return window_start

            timestamps = self._requests[resource_key]
            start_index = bisect.bisect_left(timestamps, window_start)

            if start_index < len(timestamps):
                return timestamps[start_index]

            return window_start