"""Custom decorators for logging and exception handling."""
import asyncio
import functools
import logging
from typing import Callable, Any, TypeVar, Coroutine

from shared_models import setup_logging

# Configure logging
setup_logging()
logger = logging.getLogger(__name__)

# Define TypeVars for generic type hinting
F = TypeVar('F', bound=Callable[..., Any])
Result = TypeVar('Result')
AsyncResult = TypeVar('AsyncResult', bound=Coroutine[Any, Any, Any])

def log_exceptions(func: F) -> F:
    """Decorator for logging exceptions in sync/async functions.

    Args:
        func: Function to decorate (sync or async)

    Returns:
        Wrapped function with exception logging
    """
    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Exception in async function '{func.__name__}': {e}", exc_info=True)
                raise
        return async_wrapper  # type: ignore
    else:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Exception in sync function '{func.__name__}': {e}", exc_info=True)
                raise
        return sync_wrapper  # type: ignore