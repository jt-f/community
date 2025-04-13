# Broker Service

The broker service acts as a router for messages between agents, responsible for determining which agent should receive each message.

## Update: gRPC for Agent Status Updates

The broker now uses gRPC for receiving agent status updates from the server. This architectural change provides:
- Efficient streaming of agent status updates (vs. polling)
- Lower latency for status changes
- Reduced WebSocket traffic (agent status updates now come through a dedicated gRPC channel)

WebSockets are still used for general message passing, but agent status updates use a dedicated gRPC stream.

## Installation

1. Install dependencies using Poetry or pip:
   ```
   poetry install
   ```

2. Generate the gRPC client code:
   ```
   python generate_grpc.py
   ```

## Configuration

Set the following environment variables:

```
WEBSOCKET_URL=ws://localhost:8765/ws
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
```

The gRPC configuration (host and port) is received dynamically from the server during WebSocket registration.

## Usage

Start the broker service:
```
poetry run python src/broker.py
```

## Architecture 

When the broker starts:

1. It connects to the server via WebSocket and registers as a broker
2. The server responds with registration confirmation and gRPC configuration (host, port)
3. The broker establishes a gRPC connection to receive streaming agent status updates
4. WebSocket connection remains active for general message routing

Messages flow as follows:
1. Incoming messages arrive via RabbitMQ (`broker_input_queue`)
2. Broker routes messages to appropriate agents based on internal agent status registry
3. Routed messages are published to `server_input_queue` for delivery

The broker maintains a local registry of agent statuses, which is kept in sync with the server via the gRPC stream.

## Components

### WebSocket Client
- Handles broker registration and general messaging with the server

### gRPC Client
- Receives streaming agent status updates from the server
- Manages reconnection and error handling for the gRPC connection

### RabbitMQ Consumers 
- Process messages from various queues
- Route messages between agents 