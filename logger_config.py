import logging
import logging.handlers
import json
import os
from datetime import datetime
from typing import Dict, Any


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }

        # Add extra fields if present
        if hasattr(record, 'resource_key'):
            log_entry['resource_key'] = record.resource_key
        if hasattr(record, 'sleep_time'):
            log_entry['sleep_time'] = record.sleep_time
        if hasattr(record, 'request_count'):
            log_entry['request_count'] = record.request_count
        if hasattr(record, 'worker_id'):
            log_entry['worker_id'] = record.worker_id
        if hasattr(record, 'backend_type'):
            log_entry['backend_type'] = record.backend_type
        if hasattr(record, 'rate_limit_config'):
            log_entry['rate_limit_config'] = record.rate_limit_config
        if hasattr(record, 'limit_type'):
            log_entry['limit_type'] = record.limit_type
        if hasattr(record, 'max_requests'):
            log_entry['max_requests'] = record.max_requests
        if hasattr(record, 'time_window'):
            log_entry['time_window'] = record.time_window

        return json.dumps(log_entry)


def setup_logging(log_level: str = "INFO") -> Dict[str, logging.Logger]:
    """
    Set up comprehensive logging system.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Dictionary of configured loggers
    """
    # Create logs directory if it doesn't exist
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Console handler with readable format
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)

    # JSON file handler for all logs (overwrite on each run)
    json_handler = logging.FileHandler(
        os.path.join(log_dir, 'rate_limiter.jsonl'),
        mode='w'  # Overwrite mode - fresh logs on each restart
    )
    json_handler.setFormatter(JSONFormatter())
    json_handler.setLevel(logging.DEBUG)

    # Performance log handler (overwrite on each run)
    perf_handler = logging.FileHandler(
        os.path.join(log_dir, 'performance.log'),
        mode='w'  # Overwrite mode
    )
    perf_formatter = logging.Formatter(
        '%(asctime)s - %(message)s'
    )
    perf_handler.setFormatter(perf_formatter)
    perf_handler.setLevel(logging.INFO)

    # Error log handler (overwrite on each run)
    error_handler = logging.FileHandler(
        os.path.join(log_dir, 'errors.log'),
        mode='w'  # Overwrite mode
    )
    error_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s\n%(pathname)s:%(lineno)d'
    )
    error_handler.setFormatter(error_formatter)
    error_handler.setLevel(logging.ERROR)

    # Add handlers to root logger
    root_logger.addHandler(console_handler)
    root_logger.addHandler(json_handler)
    root_logger.addHandler(error_handler)

    # Create specialized loggers
    loggers = {
        'main': logging.getLogger('rate_limiter.main'),
        'backend': logging.getLogger('rate_limiter.backend'),
        'performance': logging.getLogger('rate_limiter.performance'),
        'test': logging.getLogger('rate_limiter.test'),
    }

    # Add performance handler to performance logger
    loggers['performance'].addHandler(perf_handler)
    loggers['performance'].propagate = False  # Don't propagate to root

    return loggers


def log_rate_limit_event(logger: logging.Logger, event_type: str, resource_key: str,
                        sleep_time: float = None, request_count: int = None,
                        backend_type: str = None, **kwargs):
    """
    Log rate limiting events with structured data.

    Args:
        logger: Logger instance to use
        event_type: Type of event (request, rate_limited, config_updated, etc.)
        resource_key: Resource being rate limited
        sleep_time: Sleep time required (if applicable)
        request_count: Current request count (if applicable)
        backend_type: Backend type (memory, redis)
        **kwargs: Additional context data
    """
    extra_data = {
        'resource_key': resource_key,
        'event_type': event_type
    }

    if sleep_time is not None:
        extra_data['sleep_time'] = sleep_time
    if request_count is not None:
        extra_data['request_count'] = request_count
    if backend_type is not None:
        extra_data['backend_type'] = backend_type

    extra_data.update(kwargs)

    message = f"{event_type.upper()}: {resource_key}"
    if sleep_time is not None:
        message += f" (sleep: {sleep_time:.3f}s)"
    if request_count is not None:
        message += f" (count: {request_count})"

    logger.info(message, extra=extra_data)


def log_performance_metrics(logger: logging.Logger, operation: str, duration: float,
                          resource_key: str = None, **metrics):
    """
    Log performance metrics.

    Args:
        logger: Logger instance to use
        operation: Operation being measured
        duration: Duration in seconds
        resource_key: Resource key if applicable
        **metrics: Additional performance metrics
    """
    extra_data = {
        'operation': operation,
        'duration_seconds': duration
    }

    if resource_key:
        extra_data['resource_key'] = resource_key

    extra_data.update(metrics)

    message = f"PERF: {operation} took {duration:.4f}s"
    if resource_key:
        message += f" for {resource_key}"

    logger.info(message, extra=extra_data)