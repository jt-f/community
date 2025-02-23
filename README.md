# Community Flow - Agent Monitoring Dashboard

A real-time agent monitoring system with message flow visualization built with React and FastAPI. This application provides both a flow-based visualization of message exchanges and a comprehensive dashboard for monitoring agent states and activities.

## Features

### 1. Dual View Interface
- **Flow View**: Real-time visualization of message exchanges between agents
- **Dashboard View**: Detailed monitoring of agent states and activities

### 2. Agent Monitoring
- Real-time agent status tracking
- Message queue visualization
- Agent capability overview
- Status distribution analytics
- Interactive agent cards

### 3. Real-time Communication
- WebSocket-based real-time updates
- Automatic reconnection handling
- Message history tracking
- Bi-directional communication

### 4. Visualization Components
- Message flow graph
- Queue size charts
- Status distribution pie charts
- Agent status cards
- Message history timeline

## Tech Stack

### Frontend
- React 18
- Material-UI 5.15
- ReactFlow for graph visualization
- Recharts for data visualization
- Zustand for state management
- WebSocket for real-time communication

### Backend
- FastAPI
- WebSockets
- Pydantic for data validation
- Uvicorn ASGI server

## Getting Started

### Prerequisites
- Node.js 16 or higher
- Python 3.8 or higher
- Poetry (Python dependency management)

### Installation

1. **Backend Setup**
   ```bash
   cd community/backend
   poetry install
   ```

2. **Frontend Setup**
   ```bash
   cd community/frontend
   npm install
   ```

### Running the Application

1. **Start the Backend Server**
   ```bash
   cd community/backend
   poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
   The backend server will start on `http://172.19.36.55:8000`

2. **Start the Frontend Development Server**
   ```bash
   cd community/frontend
   npm start
   ```
   The frontend will be available at `http://172.19.36.55:3000`

## Usage

### Flow View
- Shows real-time message exchanges between agents
- Animated edges represent active communications
- Interactive node positioning
- Zoom and pan controls

### Dashboard View
- Agent Status Cards
  - Current status
  - Queue size
  - Last activity
  - Capabilities list
  
- Monitoring Charts
  - Queue size distribution
  - Agent status distribution
  - Message history timeline

### WebSocket Communication
The application uses WebSocket connections for:
- Real-time agent state updates
- Message broadcasting
- Connection status monitoring
- Automatic reconnection handling

## Development

### Project Structure
```
community/
├── backend/
│   ├── src/
│   │   ├── app.py           # FastAPI application
│   │   ├── agent.py         # Agent base class
│   │   ├── community.py     # Community management
│   │   └── test_agents.py   # Test agent implementations
│   └── pyproject.toml       # Python dependencies
└── frontend/
    ├── src/
    │   ├── components/      # React components
    │   ├── store/          # Zustand state management
    │   └── App.js          # Main application
    └── package.json        # JavaScript dependencies
```

### Key Components
- **AgentDashboard**: Main dashboard component
- **MessageFlow**: Flow visualization
- **AgentCard**: Individual agent status cards
- **QueueChart**: Message queue visualization
- **StatusDistribution**: Agent status pie chart
- **MessageHistory**: Communication timeline

## Configuration

### Backend
- WebSocket server port: 8000
- CORS settings: All origins allowed (development)
- Logging level: Configurable via environment

### Frontend
- WebSocket connection: `ws://172.19.36.55:8000/ws`
- Reconnection attempts: 10
- Reconnection interval: 2 seconds
- Message history limit: 20 messages

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 

REACT_APP_WS_URL=ws://172.19.36.55:8000/ws
REACT_APP_API_URL=http://172.19.36.55:8000/api 