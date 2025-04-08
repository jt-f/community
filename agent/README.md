# Agent

This agent connects to a central server via WebSocket for status and control, and uses RabbitMQ for message processing. When a message is received from its dedicated RabbitMQ queue, the agent uses the Mistral AI API to generate a response and sends it back via the broker.

## Prerequisites

- Python 3.13 or newer (as specified in pyproject.toml)
- RabbitMQ server running
- WebSocket server (the central server component) running
- Poetry for dependency management
- Mistral AI API Key

## Installation

1.  Navigate to the `agent` directory.
2.  Create a virtual environment (optional but recommended):
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```
3.  Install dependencies using Poetry:
    ```bash
    poetry install
    ```

## Configuration

1.  **Mistral API Key**: The agent requires a Mistral API key to function. Set the following environment variable:
    ```bash
    export MISTRAL_API_KEY='YOUR_MISTRAL_API_KEY'
    ```
    Replace `YOUR_MISTRAL_API_KEY` with your actual key. Consider using a `.env` file and `python-dotenv` for easier management in development.

2.  **Model Selection (Optional)**: You can specify a different Mistral model by setting the `MISTRAL_MODEL` environment variable. The default is `mistral-small-latest`. See `agent/src/config.py`.

## Usage

Ensure the environment variables (especially `MISTRAL_API_KEY`) are set.

Run the agent with a unique name:

```bash
poetry run python src/agent.py --name "MistralAgent"
```

### Command-line Arguments

-   `--id`: Unique identifier for this agent (optional, auto-generated if not provided)
-   `--name`: Human-readable name for this agent (required)
-   `--ws-url`: WebSocket server URL (default: fetched from environment or defaults to "ws://localhost:8765/ws")
-   `--rabbitmq-host`: RabbitMQ server host (default: fetched from environment or defaults to "localhost")

Example with custom options:

```bash
poetry run python src/agent.py --id agent_mistral_1 --name "Mistral Agent Alpha" --ws-url "ws://server.example.com:8765/ws" --rabbitmq-host "rabbitmq.example.com"
```

## How It Works

1.  The agent connects to the WebSocket server for status updates and control (like PING/PONG).
2.  It registers itself with the server by sending a `REGISTER_AGENT` message and receives a unique server-assigned ID.
3.  It connects to RabbitMQ.
4.  It declares a unique RabbitMQ queue based on its server-assigned ID.
5.  It starts consuming messages from its dedicated queue in a separate thread.
6.  When a message is received from the queue:
    -   It pauses for a configured delay (currently 10 seconds).
    -   It sends the message content to the configured Mistral AI model via the API.
    -   It receives the generated text response from Mistral.
    -   It formats the LLM response into a `REPLY` message.
    -   It publishes the `REPLY` message to the `broker_input_queue` for the server/broker to handle.
7.  The agent responds to `PING` messages from the server on the WebSocket to maintain its online status.

## Customization

-   The core LLM interaction logic is within the `generate_response` method in `agent/src/agent.py`.
-   API key and model are configured via environment variables (see `agent/src/config.py`).

## Shutdown

The agent will attempt to gracefully shut down when:
-   It receives a SIGINT or SIGTERM signal (e.g., Ctrl+C).
-   It receives a `SHUTDOWN` message from the server via WebSocket (if implemented on the server).
