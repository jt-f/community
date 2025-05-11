"""Custom decorators for logging and potentially other cross-cutting concerns."""

import asyncio
import functools
import logging

from shared_models import setup_logging

setup_logging() # Call setup_logging without arguments
logger = logging.getLogger(__name__)
logger.propagate = False  # Prevent messages reaching the root logger


def log_exceptions(func):
    """
    Decorator to log exceptions in both async and sync functions.
    Logs the exception with function name and re-raises it.
    """
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        """Wrapper for synchronous functions."""
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Exception in synchronous function {func.__name__}: {e}", exc_info=True)
            raise

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        """Wrapper for asynchronous functions."""
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Exception in asynchronous function {func.__name__}: {e}", exc_info=True)
            raise

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper