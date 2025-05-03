# Shared Models

This directory contains Python data models (Pydantic `BaseModel`) and enumerations (`Enum`) shared across the different Python-based components (Server, Broker, Agent) of the Agent Communication System.

Using these shared models ensures consistency in data structures and message types throughout the application.

For details on setting up dependencies and the overall project structure, refer to the main [Project README](../../README.md) and the [Getting Started Guide](../../GETTING_STARTED.md).

## Contents

-   `shared_models.py`: Defines the core data structures and enumerations.

## Key Definitions

Refer to the source code in `shared_models.py` for the most up-to-date definitions of:

-   **Enumerations:** `MessageType`, `ResponseStatus`
-   **Pydantic Models:** `ChatMessage`, `AgentRegistrationMessage`, `AgentRegistrationResponse`, `AgentStatus`, `AgentStatusUpdate`
-   **Helper Functions:** `create_text_message`, `create_reply_message`

## Usage

Other Python components (Server, Broker, Agent) install this package as a local path dependency using Poetry:

```toml
# In the pyproject.toml of the consuming service (e.g., server/pyproject.toml)
[tool.poetry.dependencies]
python = ">=3.13"
# ... other dependencies
shared-models = { path = "../shared_models", develop = true }
```

Then run `poetry install` in the consuming service's directory.

Imports are standard:

```python
from shared_models import MessageType, ChatMessage, AgentStatus

# Example usage
new_message = ChatMessage.create(sender_id="user1", text_payload="Hello!")
status_update = AgentStatusUpdate(agents=[...])
```
