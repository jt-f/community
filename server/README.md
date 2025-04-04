poetry run python src/main.py

# Agent Communication Server

This directory contains the Python FastAPI server responsible for managing WebSocket connections between frontends, agents, and the message broker. It orchestrates communication and maintains the status of connected agents.

## Core Responsibilities

*   Accepts WebSocket connections from Frontends, Agents, and the Broker.
*   Handles registration messages (`REGISTER_FRONTEND`, `REGISTER_AGENT`, `REGISTER_BROKER`).
*   Forwards chat messages (`TEXT`, `REPLY`, `SYSTEM`) received via WebSocket to the Broker via a RabbitMQ `incoming_messages_queue`.
*   Receives routed messages/responses from the Broker via a RabbitMQ `server_response_queue`.
*   Forwards messages from RabbitMQ to the correct WebSocket client (Frontend or Agent) based on routing information provided by the Broker.
*   Manages agent presence:
    *   Sends periodic `PING` messages to connected Agents via WebSocket.
    *   Listens for `PONG` responses to update `last_seen` status.
    *   Marks agents as offline if they disconnect or fail to respond to pings.
    *   Broadcasts agent status updates (`AGENT_STATUS_UPDATE`) to connected Frontends and the Broker via WebSocket.
*   Sends full lists of *active* agents to the Broker via the RabbitMQ `agent_metadata_queue` upon Broker registration and handles agent disconnection notifications.
*   Advertises its availability via the RabbitMQ `server_advertisement_queue`.

## Project Structure (`src/`)

*   `main.py`: FastAPI application setup, entry point, lifespan management, CORS, Uvicorn runner.
*   `config.py`: Configuration constants (ports, queues, timeouts).
*   `state.py`: Shared application state (connections, statuses).
*   `websocket_handler.py`: Handles WebSocket connections, parses incoming messages, and dispatches them to specific handler functions based on message type.
*   `rabbitmq_utils.py`: Functions for interacting with RabbitMQ (publishing, connecting).
*   `agent_manager.py`: Functions for managing agent status, history, broadcasting updates, and handling disconnections.
*   `services.py`: Background asyncio tasks (RabbitMQ consumer, agent pinger, periodic status broadcaster).
*   `utils.py`: Utility functions (signal handling, graceful shutdown).

## Communication Flows (Mermaid Diagrams)

*(Note: RMQ = RabbitMQ)*

### 1. Client Connection & Registration

```mermaid
sequenceDiagram
    autonumber
    participant C as Client (FE/Ag/Bkr)
    participant Srv as Server
    participant Bkr as Broker
    participant RMQ as RabbitMQ Queues

    C->>+Srv: WebSocket Connect (/ws)
    Srv-->>-C: WebSocket Accept

    alt Frontend Registration
        C->>Srv: Send REGISTER_FRONTEND (WS)
        Note over Srv: Add WS to frontend_connections
        Srv->>C: Broadcast AGENT_STATUS_UPDATE (Full List) (WS)
    else Agent Registration
        C->>Srv: Send REGISTER_AGENT (WS) { agent_id, agent_name }
        Note over Srv: Add WS to agent_connections[agent_id],\nUpdate agent_statuses[agent_id]
        Srv-->>C: Send REGISTER_AGENT_RESPONSE (WS) { status: SUCCESS }
        Srv->>RMQ: Publish REGISTER_AGENT (agent_metadata_queue)
        Srv->>Srv: Trigger Full Status Broadcast
        Srv->>Bkr: Broadcast AGENT_STATUS_UPDATE (WS)
        Srv->>C: Broadcast AGENT_STATUS_UPDATE (WS) (To all FE clients)
    else Broker Registration
        C->>Srv: Send REGISTER_BROKER (WS)
        Note over Srv: Store WS in broker_connection
        Srv->>RMQ: Publish AGENT_STATUS_UPDATE (Active Agents Only) (agent_metadata_queue)
    end

```

### 2. Frontend Sending Message to Agent

```mermaid
sequenceDiagram
    autonumber
    participant FE as Frontend
    participant Srv as Server
    participant Bkr as Broker
    participant Ag as Agent
    participant RMQ as RabbitMQ Queues

    FE->>Srv: Send TEXT Message (WS) { receiver: 'broker', sender: FE_user_id, text: "Hi!" }
    Note over Srv: Add internal _client_id
    Srv->>RMQ: Publish TEXT Message (incoming_messages_queue) { ..., _client_id: Srv_FE_conn_id }
    Note over Bkr: Consume from incoming_messages_queue
    Note over Bkr: Determine target Agent X based on logic/receiver_id
    Bkr->>RMQ: Publish TEXT Message (server_response_queue) { ..., _target_agent_id: AgentX_id }
    Note over Srv: Consume from server_response_queue
    Note over Srv: Find AgentX WebSocket using _target_agent_id
    Srv->>Ag: Forward TEXT Message (WS) { sender: FE_user_id, text: "Hi!" }
```

### 3. Agent Replying to Frontend

```mermaid
sequenceDiagram
    autonumber
    participant FE as Frontend
    participant Srv as Server
    participant Bkr as Broker
    participant Ag as Agent
    participant RMQ as RabbitMQ Queues

    Ag->>Srv: Send REPLY Message (WS) { receiver: FE_user_id, sender: AgentX_id, text: "Got it!" }
    Note over Srv: Add internal _client_id
    Srv->>RMQ: Publish REPLY Message (incoming_messages_queue) { ..., _client_id: Srv_Ag_conn_id }
    Note over Bkr: Consume from incoming_messages_queue
    Note over Bkr: Determine target Frontend based on receiver_id or original _client_id mapping
    Bkr->>RMQ: Publish REPLY Message (server_response_queue) { ..., _client_id: Srv_FE_conn_id }
    Note over Srv: Consume from server_response_queue
    Note over Srv: Find Frontend WebSocket using _client_id
    Srv->>FE: Forward REPLY Message (WS) { sender: AgentX_id, text: "Got it!" }
```

### 4. Agent Status Updates & Pings

```mermaid
sequenceDiagram
    autonumber
    participant FE as Frontend
    participant Srv as Server
    participant Bkr as Broker (WS Connected)
    participant Ag as Agent

    loop Periodic Ping Service (every ~10s)
        Srv->>Ag: Send PING (WS)
        Ag->>Srv: Send PONG (WS) { agent_id }
        Note over Srv: Update agent_statuses[agent_id].last_seen
    end

    Note over Srv: Agent status changes (e.g., timeout, PONG received after offline) OR Periodic Broadcast Timer (~60s)
    Note over Srv: Prepare AGENT_STATUS_UPDATE (Delta or Full)
    Srv->>FE: Broadcast AGENT_STATUS_UPDATE (WS)
    Srv->>Bkr: Broadcast AGENT_STATUS_UPDATE (WS)

```

### 5. Agent Disconnection

```mermaid
sequenceDiagram
    autonumber
    participant FE as Frontend
    participant Srv as Server
    participant Bkr as Broker (WS Connected)
    participant Ag as Agent
    participant RMQ as RabbitMQ Queues

    Ag--xSrv: WebSocket Disconnect / Error
    Note over Srv: Remove Ag from active_connections, agent_connections
    Note over Srv: Mark Agent offline in agent_statuses
    Srv->>RMQ: Publish CLIENT_DISCONNECTED (agent_metadata_queue) { agent_id: AgentX_id }
    Note over Srv: Prepare AGENT_STATUS_UPDATE (Delta)
    Srv->>FE: Broadcast AGENT_STATUS_UPDATE (WS)
    Srv->>Bkr: Broadcast AGENT_STATUS_UPDATE (WS)

```

## Running the Server

```bash
cd server/src
python main.py
```

Requires Python 3.10+ and dependencies installed from `../requirements.txt`. Ensure RabbitMQ is running and accessible at the configured host/port.