poetry run python src/main.py

# Agent Communication Server

This service provides the backend infrastructure for agent communication, acting as a message router between agents, brokers, and frontend clients. It utilizes FastAPI for WebSocket handling (primarily for frontends) and gRPC for agent/broker interactions.

## Architecture Overview

*   **FastAPI & WebSockets:** Manages WebSocket connections, primarily for frontend clients (`/ws`). Handles frontend registration and chat message exchange.
*   **gRPC:** Provides services for agent registration (`AgentRegistrationService`), agent status updates (`AgentStatusService`), and potentially broker registration (`BrokerRegistrationService`). This is the primary communication channel for agents and brokers.
*   **RabbitMQ:** Used as a message bus for decoupling components. Handles message forwarding between the server, broker, and agents. Also used for server discovery and potentially broker registration notifications.
*   **Background Services:** Asynchronous tasks manage consuming messages from RabbitMQ, broadcasting status updates, and potentially other periodic tasks.

## Core Responsibilities

*   **Frontend WebSocket Management:** Accepts and manages WebSocket connections from Frontend clients. Handles `REGISTER_FRONTEND` and chat messages (`TEXT`, `REPLY`, `SYSTEM`). Forwards messages from the broker (via RabbitMQ) to the appropriate frontend client.
*   **gRPC Service Implementation:**
    *   `AgentRegistrationService`: Handles agent registration, unregistration, heartbeats (if implemented via gRPC), and command streaming/results.
    *   `AgentStatusService`: Provides streaming agent status updates to connected brokers and allows one-time status requests.
    *   `BrokerRegistrationService`: Handles broker registration requests.
*   **Message Routing (via RabbitMQ):**
    *   Receives messages from frontends (via WebSocket) and publishes them to the `broker_input_queue`.
    *   Receives messages from agents/brokers (via RabbitMQ queues like `agent_output_queue` or `broker_input_queue`) and processes them.
    *   Consumes routed messages/errors from the `server_input_queue` (published by the broker or other services).
    *   Forwards messages destined for frontends via their WebSocket connection.
    *   Forwards messages destined for specific agents by publishing to their dedicated RabbitMQ queue (`agent_queue_<agent_id>`).
*   **Agent Presence & Status Management (`agent_manager.py`, `state.py`, gRPC Services):**
    *   Maintains the canonical state of all registered agents (`state.agent_statuses`) based on gRPC registration and potentially heartbeats/connection status.
    *   Updates agent status (online/offline, last seen) based on gRPC interactions or timeouts.
    *   Broadcasts agent status updates primarily via the `AgentStatusService` gRPC stream to brokers.
    *   Broadcasts agent status updates via WebSocket (`AGENT_STATUS_UPDATE`) to connected *frontend* clients for UI display.
*   **Broker Status Management:** Tracks broker status based on gRPC connections or RabbitMQ messages (`state.broker_statuses`).
*   **Graceful Shutdown:** Handles SIGINT/SIGTERM signals for cleaning up connections, gRPC server, and background tasks.

## Project Structure (`src/`)

*   `main.py`: FastAPI application setup, entry point, lifespan management (including gRPC server start/stop), CORS, Uvicorn runner.
*   `config.py`: Configuration loaded from environment variables.
*   `state.py`: Shared application state (connection sets for frontends, agent/broker statuses, locks).
*   `websocket_handler.py`: Handles WebSocket connections *primarily for frontends*. Parses incoming frontend messages (registration, chat, status requests).
*   `rabbitmq_utils.py`: Functions for interacting with RabbitMQ.
*   `agent_manager.py`: Logic for managing agent status in `state.py` and triggering broadcasts.
*   `services.py`: Background asyncio tasks (RabbitMQ consumers, periodic status broadcaster).
*   `grpc_services.py`: Manages the gRPC server lifecycle and provides helper functions for gRPC communication (like broadcasting status).
*   `agent_registration_service.py`: gRPC Servicer implementation for agent registration.
*   `agent_status_service.py`: (Likely exists or needed) gRPC Servicer implementation for agent status.
*   `broker_registration_service.py`: (Likely exists or needed) gRPC Servicer implementation for broker registration.
*   `utils.py`: Utility functions (signal handling).
*   `protos/`: Protocol Buffer definitions for gRPC services.
*   `generated/`: Python code generated from `.proto` files.

## Prerequisites

*   Python 3.13+
*   RabbitMQ server running
*   Poetry

## Installation

1.  Navigate to the `server` directory.
2.  Create/activate a virtual environment.
3.  Install dependencies: `poetry install`
4.  Generate gRPC code: `python generate_grpc.py` (assuming this script exists)

## Configuration

Key environment variables (see `src/config.py`):

*   `RABBITMQ_HOST`, `RABBITMQ_PORT`
*   `HOST` (Uvicorn host, default: `0.0.0.0`)
*   `PORT` (Uvicorn port, default: `8765`)
*   `GRPC_HOST` (default: `localhost`)
*   `GRPC_PORT` (default: `50051`)
*   `PERIODIC_STATUS_INTERVAL` (default: 60 seconds)
*   *(Potentially others like agent timeouts if managed via gRPC heartbeats)*

## Running the Server

Ensure RabbitMQ is running.

```bash
poetry run python src/main.py
```

The server will start the FastAPI/Uvicorn server (default: `0.0.0.0:8765`) and the gRPC server (default: `localhost:50051`).

## Communication Flows (Simplified)

*(Note: RMQ = RabbitMQ, WS = WebSocket, gRPC = gRPC)*

### 1. Frontend Connection & Registration

```mermaid
sequenceDiagram
    autonumber
    participant Frontend as Frontend
    participant Srv as Server (FastAPI/WS)
    participant SrvGRPC as Server (gRPC)
    participant AgentMgr as Agent Manager

    Frontend->>+Srv: WS Connect (/ws)
    Srv-->>-Frontend: WS Accept
    Frontend->>Srv: Send REGISTER_FRONTEND (WS)
    Note over Srv: Add WS to state.frontend_connections, assign client_id (web_...)
    Srv->>Frontend: Send REGISTER_FRONTEND_RESPONSE (WS) { frontend_id }
    Note over Srv: Trigger Agent Status Broadcast
    Srv->>AgentMgr: Request Agent Status Broadcast
    AgentMgr->>SrvGRPC: Get Current Agent Status
    AgentMgr->>Srv: Send AGENT_STATUS_UPDATE (Full List) (WS) to Frontend
```

### 2. Agent Connection & Registration (via gRPC)

```mermaid
sequenceDiagram
    autonumber
    participant Agent as Agent
    participant SrvGRPC as Server (gRPC)
    participant AgentMgr as Agent Manager
    participant Broker as Broker (via gRPC)
    participant Frontend as Frontend (via WS)

    Agent->>+SrvGRPC: Connect (gRPC)
    Agent->>SrvGRPC: Call RegisterAgent RPC { agent_name, ... }
    Note over SrvGRPC: Process registration, update state.agent_statuses
    SrvGRPC-->>-Agent: Return RegisterAgent Response { success, agent_id }
    Note over SrvGRPC: Trigger Agent Status Broadcast
    SrvGRPC->>AgentMgr: Notify Agent Status Change (Agent Online)
    AgentMgr->>SrvGRPC: Broadcast AGENT_STATUS_UPDATE (gRPC Stream to Brokers)
    AgentMgr->>Frontend: Broadcast AGENT_STATUS_UPDATE (WS to Frontends)
```

### 3. Broker Connection & Status Subscription (via gRPC)

```mermaid
sequenceDiagram
    autonumber
    participant Broker as Broker
    participant SrvGRPC as Server (gRPC)
    participant AgentMgr as Agent Manager

    Broker->>+SrvGRPC: Connect (gRPC)
    Broker->>SrvGRPC: Call RegisterBroker RPC (Optional, might use RMQ)
    SrvGRPC-->>-Broker: Return RegisterBroker Response
    Broker->>SrvGRPC: Call SubscribeToAgentStatus RPC
    Note over SrvGRPC: Add Broker to list of gRPC status subscribers
    SrvGRPC-->>Broker: Stream initial AGENT_STATUS_UPDATE (Full List)
    loop Agent Status Changes
        Note over AgentMgr: Detects agent status change (connect/disconnect)
        AgentMgr->>SrvGRPC: Trigger Agent Status Broadcast
        SrvGRPC-->>Broker: Stream AGENT_STATUS_UPDATE (Delta or Full)
    end
```

### 4. Frontend Sending Message to Agent

```mermaid
sequenceDiagram
    autonumber
    participant Frontend as Frontend
    participant SrvWS as Server (FastAPI/WS)
    participant SrvRMQ as Server (RMQ Consumer)
    participant Broker as Broker (via RMQ)
    participant Agent as Agent (via RMQ)
    participant RMQ as RabbitMQ

    Frontend->>SrvWS: Send TEXT Message (WS) { sender: web_..., text: "Hi!" }
    SrvWS->>RMQ: Publish TEXT Message (broker_input_queue) { ..., _client_id: web_... }
    Broker->>RMQ: Consume TEXT Message (broker_input_queue)
    Note over Broker: Route message: Select Agent_X
    Broker->>RMQ: Publish TEXT Message (server_input_queue) { receiver: Agent_X, sender: web_..., routing_status: routed }
    SrvRMQ->>RMQ: Consume TEXT Message (server_input_queue)
    Note over SrvRMQ: Message is routed, forward to agent queue
    SrvRMQ->>RMQ: Publish TEXT Message (agent_queue_Agent_X) { receiver: Agent_X, sender: web_..., ... }
    Agent->>RMQ: Consume TEXT Message (agent_queue_Agent_X)
    Note over Agent: Process message, generate reply
    Agent->>RMQ: Publish REPLY Message (broker_input_queue) { receiver: web_..., sender: Agent_X, ... }
    Broker->>RMQ: Consume REPLY Message (broker_input_queue)
    Broker->>RMQ: Publish REPLY Message (server_input_queue) { receiver: web_..., sender: Agent_X, routing_status: routed }
    SrvRMQ->>RMQ: Consume REPLY Message (server_input_queue)
    Note over SrvRMQ: Message is routed to frontend (web_...)
    SrvRMQ->>SrvWS: Forward message to specific Frontend WS connection
    SrvWS->>Frontend: Forward REPLY Message (WS) { sender: Agent_X, ... }
```

### 5. Agent Disconnection (via gRPC)

```mermaid
sequenceDiagram
    autonumber
    participant Agent as Agent
    participant SrvGRPC as Server (gRPC)
    participant AgentMgr as Agent Manager
    participant Broker as Broker (via gRPC)
    participant Frontend as Frontend (via WS)

    Agent--xSrvGRPC: gRPC Connection Lost / UnregisterAgent RPC called
    Note over SrvGRPC: Detects disconnection / processes unregistration
    SrvGRPC->>AgentMgr: Notify Agent Status Change (Agent Offline)
    Note over AgentMgr: Update state.agent_statuses
    AgentMgr->>SrvGRPC: Broadcast AGENT_STATUS_UPDATE (gRPC Stream to Brokers)
    AgentMgr->>Frontend: Broadcast AGENT_STATUS_UPDATE (WS to Frontends)
```

## API Reference

### WebSocket Endpoints (Primarily Frontend)

*   `/ws` - Main WebSocket endpoint for frontend clients.

### gRPC Services

*   `AgentRegistrationService`: See `protos/agent_registration_service.proto`
*   `AgentStatusService`: See `protos/agent_status_service.proto`
*   `BrokerRegistrationService`: See `protos/broker_registration_service.proto`

## For Developers

To modify gRPC services:

1.  Edit the `.proto` definition(s) in `src/protos/`.
2.  Regenerate the gRPC code: `python generate_grpc.py`
3.  Update the corresponding Servicer implementation(s) in `src/`.