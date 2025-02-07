# Community Flow Visualization

A real-time message flow visualization system built with React and Flask. This application provides an interactive graph visualization of message exchanges between users and systems, with real-time WebSocket updates and a clean, modern interface.

## Prerequisites

Before you begin, ensure you have the following installed:
- Python 3.8 or higher
- Poetry (Python dependency management)
- Node.js 16 or higher (required for React frontend)
- npm (comes with Node.js)

## Tech Stack

### Frontend
- Node.js and npm for JavaScript runtime and package management
- React 18
- React Flow for graph visualization
- Socket.IO client for real-time communication
- Material-UI for styling
- Webpack 5 for bundling

### Backend
- Flask
- Flask-SocketIO for WebSocket support
- CORS for cross-origin resource sharing
- Python logging for debugging

## Getting Started

### Start the Backend Server

```bash
cd backend
poetry install
poetry run python app.py
```

The backend server will start on `http://[your-ip]:5000`

### Start the Frontend Development Server

```bash
cd frontend
npm install
npm start
```

The frontend will be available at `http://[your-ip]:3000`

### Send a Test Message

You can use the provided test script to send messages:

```bash
cd backend
poetry run python test_message.py
```

Or send a custom message using curl:

```bash
curl -X POST http://[your-ip]:5000/message \
  -H "Content-Type: application/json" \
  -d '{"from": "user", "text": "Hello, World!"}'
```

## Features

- Real-time message visualization
- Interactive graph layout
- Automatic reconnection handling
- Cross-platform compatibility
- Clean, modern UI
- Robust error handling

## Development

The application uses:
- WebSocket for real-time bi-directional communication
- React Flow for graph visualization
- Material-UI for consistent styling
- Flask's development server with threading

## Architecture

```
frontend/                 # React application
  ├── src/               # Source files
  │   ├── App.js         # Main application component
  │   └── styles.css     # Global styles
  └── public/            # Static files

backend/                  # Flask server
  ├── app.py             # Main server file
  └── test_message.py    # Message testing utility
```

## Notes

- The backend uses threading mode for WebSocket support
- CORS is configured to accept connections from any origin for development
- The frontend automatically attempts to reconnect on connection loss
- All messages are logged for debugging purposes

## License

MIT 