# Agent

This agent connects to a broker via WebSocket, registers itself, and processes messages from a dedicated RabbitMQ queue. When messages are received, the agent processes them and sends responses back through the WebSocket connection.

## Prerequisites

- Python 3.7 or newer
- RabbitMQ server
- WebSocket server (e.g., the main server/broker for the system)

## Installation

1. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the agent with a unique name:

```bash
python src/agent.py --name "MyAgent"
```

### Command-line Arguments

- `--id`: Unique identifier for this agent (optional, auto-generated if not provided)
- `--name`: Human-readable name for this agent (required)
- `--ws-url`: WebSocket server URL (default: "ws://localhost:8765/ws")
- `--rabbitmq-host`: RabbitMQ server host (default: "localhost")

Example with all options:

```bash
python src/agent.py --id agent_custom_id --name "Custom Agent" --ws-url "ws://server.example.com:8765/ws" --rabbitmq-host "rabbitmq.example.com"
```

## How It Works

1. The agent connects to the WebSocket server.
2. It registers itself by sending a `REGISTER_AGENT` message.
3. After successful registration, it connects to RabbitMQ and sets up its queue.
4. It starts consuming messages from the dedicated queue.
5. When a message is received, it processes it and sends a response via the WebSocket connection.

## Customization

To customize the agent's behavior, extend the `Agent` class and override the `generate_response` method to implement your own logic for processing messages.

## Shutdown

The agent will gracefully shut down when:
- It receives a SIGINT or SIGTERM signal (e.g., Ctrl+C).
- It receives a `SHUTDOWN` message from the broker via WebSocket.
