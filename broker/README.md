# Broker

This component acts as a message broker and agent registry within the system. It uses RabbitMQ for message queuing and WebSockets to communicate with the central server for agent status updates and keepalive checks.

## Key Responsibilities:

-   **Agent Registry:** Maintains a list of registered agents and their online/offline status (`registered_agents`).
-   **Message Routing:** Receives messages (TEXT, REPLY, SYSTEM) from agents via the `broker_input_queue` and routes them randomly to another available online agent.
-   **Error Handling:** Forwards ERROR messages received from agents directly to the server.
-   **Status Updates:** Receives `AGENT_STATUS_UPDATE` messages from the server via WebSocket and updates its internal agent registry.
-   **Keepalive:** Responds to `PING` and `SERVER_HEARTBEAT` messages from the server with `PONG` messages to maintain its WebSocket connection.
-   **Server Communication:** Publishes routed messages and error messages to the `broker_output_queue` for the server to process.

## Prerequisites

-   Python 3.13 or newer (as specified in pyproject.toml)
-   RabbitMQ server running
-   WebSocket server (the central server component) running
-   Poetry for dependency management

## Installation

1.  Navigate to the `broker` directory.
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

The broker reads connection details for RabbitMQ and the WebSocket server from environment variables:

-   `RABBITMQ_HOST` (default: `localhost`)
-   `RABBITMQ_PORT` (default: `5672`)
-   `WEBSOCKET_URL` (default: `ws://localhost:8765/ws`)

These can be set in your environment or a `.env` file.

## Usage

Ensure the RabbitMQ server and the main WebSocket server are running.

Start the broker using Poetry:

```bash
poetry run python src/broker.py
```

The broker will automatically assign itself a unique ID (e.g., `broker_1234`).

## How It Works

1.  **Initialization:** Sets up logging, generates a broker ID.
2.  **RabbitMQ Setup:** Connects to RabbitMQ and sets up consumers (in separate threads) for:
    -   `broker_input_queue`: Handles incoming messages from agents.
    -   `agent_metadata_queue`: Handles control messages like agent registration/disconnection (Note: This seems less used now as registration flows via WebSocket).
    -   `server_advertisement_queue`: Listens for server availability messages.
3.  **WebSocket Connection:** Connects to the central server's WebSocket endpoint (`/ws`).
4.  **Registration:** Sends a `REGISTER_BROKER` message to the server and receives its assigned ID.
5.  **WebSocket Listening Loop:**
    -   Receives `AGENT_STATUS_UPDATE` messages and updates the `registered_agents` dictionary.
    -   Responds to `PING` and `SERVER_HEARTBEAT` with `PONG`.
    -   Logs other message types received on the WebSocket.
    -   Handles connection errors and attempts reconnection.
6.  **RabbitMQ Input Handling (`handle_incoming_message`):**
    -   Receives messages from `broker_input_queue`.
    -   If TEXT/REPLY/SYSTEM: Calls `route_message`.
    -   If ERROR: Publishes directly to `broker_output_queue`.
    -   Acknowledges messages.
7.  **Message Routing (`route_message`):**
    -   Checks the list of online agents in `registered_agents` (excluding the sender).
    -   If other online agents exist, randomly selects one as the `receiver_id`.
    -   If no other agents are online, sends an ERROR message back to the server (via output queue).
    -   Publishes the message (with the determined `receiver_id`) to `broker_output_queue`.
8.  **Shutdown:** Listens for SIGINT/SIGTERM signals to gracefully shut down the WebSocket listener and RabbitMQ consumer threads.

## State

The broker maintains minimal state, primarily the `registered_agents` dictionary containing information about known agents and their online status. 