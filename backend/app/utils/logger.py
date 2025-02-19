"""
Structured logging utility with color support.
"""
import sys
import logging
from typing import Optional
import structlog
from structlog.stdlib import LoggerFactory
import colorama
from colorama import Fore, Style

# Initialize colorama for Windows support
colorama.init()

def color_level(logger, method_name, event_dict):
    """Add color to the log level."""
    level = event_dict.get("level", "unknown")
    level_colors = {
        "debug": Fore.CYAN,
        "info": Fore.GREEN,
        "warning": Fore.YELLOW,
        "error": Fore.RED,
        "critical": Fore.RED + Style.BRIGHT
    }
    
    if level.lower() in level_colors:
        color = level_colors[level.lower()]
        event_dict["level_color"] = f"{color}{level.upper()}{Style.RESET_ALL}"
        # Keep the plain level for JSON output
        event_dict["level"] = level.upper()
    
    return event_dict

def add_timestamp(logger, method_name, event_dict):
    """Add timestamp to the log event."""
    from datetime import datetime
    event_dict["timestamp"] = datetime.now().isoformat()
    return event_dict

def console_formatter(_, __, event_dict):
    """Format log messages for console output."""
    level_color = event_dict.pop("level_color", event_dict["level"])
    timestamp = event_dict["timestamp"]
    event = event_dict.get("event", "")
    
    return f"{timestamp} [{level_color}] {event}"

def setup_logging(level: Optional[str] = None):
    """Set up structured logging with color support."""
    if level is None:
        level = "INFO"
    
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        add_timestamp,
        color_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            console_formatter,
        ],
        context_class=dict,
        logger_factory=LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Set up root logger
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper())
    )

def get_logger(name: str) -> structlog.BoundLogger:
    """Get a logger instance for the given name."""
    return structlog.get_logger(name)

# Set up logging on module import
setup_logging() 