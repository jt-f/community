# Shared Models

This directory contains Python data models and enumerations shared across the different components (server, broker, agent, potentially frontend if using Python) of the Agent Communication System. Using shared models ensures consistency in data structures and message types throughout the application.

## Contents

-   `shared_models.py`: Defines the core data structures using Pydantic `BaseModel` and standard Python `Enum`.

## Key Definitions

### Enumerations

-   **`MessageType(str, Enum)`**: Defines the valid types for messages exchanged within the system (e.g., `AGENT_STATUS_UPDATE`, `CLIENT_DISCONNECTED`, `ERROR`, `REGISTER_FRONTEND`, `REGISTER_FRONTEND_RESPONSE`, `REQUEST_AGENT_STATUS`, `REPLY`, `SYSTEM`, `TEXT`).
-   **`ResponseStatus(str, Enum)`**: Defines simple status values for response messages (e.g., `SUCCESS`, `ERROR`).

### Pydantic Models (`BaseModel`)

-   **`ChatMessage`**: Represents a standard chat message with fields like `message_id`, `sender_id`, `text_payload`, `send_timestamp`, `message_type`, and optional `in_reply_to_message_id`.
    -   Includes helper class methods (`create`, `from_dict`) and instance methods (`to_dict`).
-   **`AgentRegistrationMessage`**: Structure for the message sent by an agent *to the server* during registration (now contains primarily `agent_name`, as `agent_id` is assigned by the server).
-   **`AgentRegistrationResponse`**: Structure for the server's response to an agent's registration attempt, including `status`, assigned `agent_id`, and a `message`.
-   **`AgentStatus`**: Represents the status information for a single agent, including `agent_id`, `agent_name`, `is_online`, and `last_seen` timestamp.
-   **`AgentStatusUpdate`**: Structure for the message broadcast by the server containing a list of `AgentStatus` objects for multiple agents. Includes `message_type` and a list of `AgentStatus` objects.

### Helper Functions

-   `create_text_message(...)`: Convenience function to create a `ChatMessage` instance with `message_type=TEXT`.
-   `create_reply_message(...)`: Convenience function to create a `ChatMessage` instance with `message_type=REPLY`, automatically setting the `in_reply_to_message_id`.

## Usage

Other components (server, broker, agent) install this package as a local path dependency (e.g., using Poetry or pip editable installs). They can then import the necessary models and enums:

```python
from shared_models import MessageType, ChatMessage, AgentStatus

# Example usage
new_message = ChatMessage.create(sender_id="user1", text_payload="Hello!")
status_update = AgentStatusUpdate(agents=[...])
```

## Installation as Dependency

Typically, this package is installed using Poetry by specifying a path dependency in the `pyproject.toml` file of the consuming package (server, broker, agent):

```toml
[tool.poetry.dependencies]
python = ">=3.13"
# ... other dependencies
shared-models = { path = "../shared_models", develop = true }
```

Then run `poetry install` in the consuming package's directory.
