"""
Utility functions for message handling.
"""
from typing import Any

def truncate_message(message: Any, max_length: int = 20) -> str:
    """Truncate message content for logging purposes."""
    if not message:
        return "None"
    
    # Handle different message formats
    if isinstance(message, dict):
        if 'content' in message:
            content = message['content']
            if isinstance(content, dict) and 'text' in content:
                text = content['text']
                return f"{text[:max_length]}..." if len(text) > max_length else text
            return f"{str(content)[:max_length]}..." if len(str(content)) > max_length else str(content)
        return str(message)[:30] + "..."
    
    # Handle Message objects
    if hasattr(message, 'content'):
        content = message.content
        if isinstance(content, dict) and 'text' in content:
            text = content['text']
            return f"{text[:max_length]}..." if len(text) > max_length else text
        return f"{str(content)[:max_length]}..." if len(str(content)) > max_length else str(content)
    
    # Default case
    message_str = str(message)
    return f"{message_str[:max_length]}..." if len(message_str) > max_length else message_str 