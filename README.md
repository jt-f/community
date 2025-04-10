# Agent Communication System

This project demonstrates a distributed system featuring a central server, message broker, agents (potentially LLM-powered), and a web frontend, communicating via WebSockets and RabbitMQ.

## Components

-   **Server (`/server`):** FastAPI server managing WebSocket connections, agent status, and message orchestration. [See Server README](./server/README.md)
-   **Broker (`/broker`):** Handles message routing between agents using RabbitMQ and maintains a registry of online agents. [See Broker README](./broker/README.md)
-   **Agent (`/agent`):** Connects to the server and broker, processes messages (currently using Mistral AI), and responds. [See Agent README](./agent/README.md)
-   **Frontend (`/frontend`):** React/Vite web application for real-time chat and viewing agent status. [See Frontend README](./frontend/README.md)
-   **Shared Models (`/shared_models`):** Common Pydantic models and Enums used across Python components. [See Shared Models README](./shared_models/README.md)

## Prerequisites

-   Docker (for RabbitMQ)
-   Python 3.13+ & Poetry
-   Node.js & npm/yarn
-   Environment variables set as required by each component (e.g., `MISTRAL_API_KEY` for the agent).

## Running the System

Run each component in a separate terminal.

### 1. RabbitMQ (using Docker)
```bash
docker run -it --rm --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
# Management UI: http://localhost:15672/ (guest/guest)
```

### 2. WebSocket Server
```bash
cd server
source ~/.bashrc
poetry run python src/main.py
```

### 3. Frontend
```bash
cd frontend
npm run dev
# Access via http://localhost:5173 (or as indicated by Vite)
```

### 4. Message Routing Broker
```bash
cd broker
source ~/.bashrc
poetry run python src/broker.py 
```

### 5. Agent(s)
```bash
cd agent
source ~/.bashrc
poetry run python src/agent.py --name "AgentName1"

# In another terminal (optional, for multiple agents):
cd agent
source ~/.bashrc
poetry run python src/agent.py --name "AgentName2"