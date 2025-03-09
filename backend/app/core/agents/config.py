
#Configuration for agent prompts and settings.
ANALYST_CONFIG = {
    "model": "mistral-large-latest",  # Default model
    "provider": "mistral",         # Default provider (ollama, mistral, anthropic, openai, together)
    "temperature": 0.7,           # Default temperature
    "prompts": {
        "default": "You are a helpful assistant. Please respond to the following: {message}",
        "technical": "You are a technical expert. Analyze the following technical question: {message}",
        "data": "You are a data analyst. Analyze the following data question: {message}",
        "chat": "You are a friendly conversational agent. Respond to: {message}"
    }
}

SYSTEM_CONFIG = {
    "think_interval": 300,  # 5 minutes between system status updates
}

HUMAN_CONFIG = {
    "capabilities": [
        "user_interaction",
        "message_sending",
        "command_execution",
        "task_delegation"
    ]
}
