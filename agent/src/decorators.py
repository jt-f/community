import asyncio
import functools
import logging

from shared_models import setup_logging

logger = setup_logging(__name__)

def log_exceptions(func):
    """
    Decorator to log exceptions in both async and sync functions.
    Logs the exception with function name and re-raises it.
    """
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Exception in {func.__name__}: {e}", exc_info=True)
            raise

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Exception in {func.__name__}: {e}", exc_info=True)
            raise

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper