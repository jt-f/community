import functools
import logging
import time
import asyncio
from shared_models import setup_logging

# Configure logging
setup_logging()
logger = logging.getLogger(__name__) # Get logger for this module

def log_function_call(func):
    """A decorator to log function calls, arguments, and execution time."""
    @functools.wraps(func)
    async def wrapper_async(*args, **kwargs):
        func_name = func.__name__
        # Log entry with arguments
        args_repr = [repr(a) for a in args]
        kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
        signature = ", ".join(args_repr + kwargs_repr)
        logger.debug(f"Entering {func_name}({signature})")
        start_time = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            end_time = time.perf_counter()
            logger.debug(f"Exiting {func_name} after {end_time - start_time:.4f}s. Result: {result!r}")
            return result
        except Exception as e:
            logger.exception(f"Exception in {func_name}")
            raise

    @functools.wraps(func)
    def wrapper_sync(*args, **kwargs):
        func_name = func.__name__
        # Log entry with arguments
        args_repr = [repr(a) for a in args]
        kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]
        signature = ", ".join(args_repr + kwargs_repr)
        logger.debug(f"Entering {func_name}({signature})")
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            end_time = time.perf_counter()
            logger.debug(f"Exiting {func_name} after {end_time - start_time:.4f}s. Result: {result!r}")
            return result
        except Exception as e:
            logger.exception(f"Exception in {func_name}")
            raise

    if asyncio.iscoroutinefunction(func):
        return wrapper_async
    else:
        return wrapper_sync