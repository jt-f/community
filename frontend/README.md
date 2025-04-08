# Frontend

This is the web-based frontend client for the Agent Communication System. It provides a real-time chat interface and displays the status of connected agents.

Built with React, TypeScript, and Vite.

## Features

-   **Real-time Chat:** Connects to the server via WebSocket for sending and receiving chat messages.
-   **Agent Status Panel:** Displays a list of registered agents and their online/offline status, updated in real-time.
-   **WebSocket Management:** Handles WebSocket connection, automatic reconnection attempts, and keepalive (via server heartbeats).
-   **Context-based State Sharing:** Uses React Context (`WebSocketContext`) to share WebSocket connection state and received messages between components.
-   **Agent State Management:** Utilizes Zustand (`agentStore.ts`) for managing the list of agents and their statuses received from the server.
-   **Modern UI:** Simple, clean interface styled using CSS variables and potentially modern CSS features.

## Prerequisites

-   Node.js (v18 or later recommended)
-   npm or yarn
-   A running instance of the backend server component.

## Installation

1.  Navigate to the `frontend` directory.
2.  Install dependencies:
    ```bash
    npm install
    # or
    # yarn install
    ```

## Configuration

The frontend requires the WebSocket URL of the backend server. This is configured via environment variables:

1.  Create a `.env` file in the `frontend` root directory (if it doesn't exist).
2.  Add the following line, replacing the URL with your actual server's WebSocket endpoint:
    ```env
    VITE_WS_URL=ws://localhost:8765/ws
    ```

See `src/config.ts` for how environment variables are loaded.

## Running the Development Server

To start the frontend in development mode with hot reloading:

```bash
npm run dev
# or
# yarn dev
```

This will typically start the server on `http://localhost:5173` (or the next available port).

## Building for Production

To create an optimized production build:

```bash
npm run build
# or
# yarn build
```

The production-ready files will be placed in the `dist` directory. You can serve these files using a static file server (like `serve` or Nginx).

```bash
npm install -g serve
serve -s dist
```

## Core Components

-   **`src/main.tsx`**: Entry point of the application.
-   **`src/App.tsx`**: Main application component, sets up routing or main layout.
-   **`src/components/ChatUI.tsx`**: Orchestrates the main UI, manages WebSocket connection, context provider, and renders `Chat` and `AgentPanel`.
-   **`src/components/Chat.tsx`**: Implements the chat message display and input area. Consumes `WebSocketContext`.
-   **`src/components/AgentPanel.tsx`**: Displays the list of agents and their status. Consumes `WebSocketContext` and uses `agentStore`.
-   **`src/store/agentStore.ts`**: Zustand store for managing agent state.
-   **`src/config.ts`**: Loads and exports configuration (like WebSocket URL).
-   **`src/types/message.ts`**: Defines shared TypeScript types for messages.

## WebSocket Communication

-   Managed primarily within `ChatUI.tsx`.
-   Connects to the URL specified by `VITE_WS_URL`.
-   Registers itself as a `REGISTER_FRONTEND` client upon connection.
-   Listens for incoming messages (`AGENT_STATUS_UPDATE`, `TEXT`, `REPLY`, `ERROR`, etc.).
-   Handles `SERVER_HEARTBEAT` messages from the server to maintain connection awareness.
-   Provides a `sendMessage` function via `WebSocketContext` for child components to send messages.
-   Includes logic for automatic reconnection on disconnect.

## Hot Module Replacement (HMR)

This project uses Vite's built-in HMR, which provides instant updates as you edit your code. HMR is enabled by default and works out of the box.

### How it works

- When you make changes to your React components, the changes will be reflected immediately in the browser without a full page reload
- Component state is preserved during updates
- The WebSocket connection will automatically reconnect if needed

### Custom HMR Configuration

If you need to customize HMR behavior, you can modify the `vite.config.ts` file:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    hmr: {
      // Enable HMR overlay
      overlay: true,
      // Custom HMR protocol
      protocol: 'ws',
      // Custom HMR host
      host: 'localhost',
      // Custom HMR port
      port: 24678
    }
  }
})
```

### Troubleshooting HMR

If HMR isn't working as expected:

1. Make sure you're not using any browser extensions that might interfere with WebSocket connections
2. Check if your firewall is blocking WebSocket connections
3. Try clearing your browser cache
4. Ensure you're running the latest version of the development server

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   └── Chat.tsx       # Main chat component
│   ├── App.tsx           # Root component
│   ├── main.tsx          # Application entry point
│   └── index.css         # Global styles
├── public/               # Static assets
└── package.json          # Project dependencies and scripts
```

---

# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react/README.md) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default tseslint.config({
  extends: [
    // Remove ...tseslint.configs.recommended and replace with this
    ...tseslint.configs.recommendedTypeChecked,
    // Alternatively, use this for stricter rules
    ...tseslint.configs.strictTypeChecked,
    // Optionally, add this for stylistic rules
    ...tseslint.configs.stylisticTypeChecked,
  ],
  languageOptions: {
    // other options...
    parserOptions: {
      project: ['./tsconfig.node.json', './tsconfig.app.json'],
      tsconfigRootDir: import.meta.dirname,
    },
  },
})
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default tseslint.config({
  plugins: {
    // Add the react-x and react-dom plugins
    'react-x': reactX,
    'react-dom': reactDom,
  },
  rules: {
    // other rules...
    // Enable its recommended typescript rules
    ...reactX.configs['recommended-typescript'].rules,
    ...reactDom.configs.recommended.rules,
  },
})
```
