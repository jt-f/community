# WebSocket Chat Application

A real-time chat application built with React, TypeScript, and Vite that connects to a WebSocket server.

## Prerequisites

- Node.js (v14 or higher)
- npm (v6 or higher)
- A running WebSocket server (the Python FastAPI server should be running on port 8765)

## Installation

1. Clone the repository
2. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
3. Install dependencies:
   ```bash
   npm install
   ```

## Development

1. Start the development server:
   ```bash
   npm run dev
   ```
2. Open your browser and navigate to the URL shown in the terminal (typically http://localhost:5173)
3. Make sure your WebSocket server is running on port 8765
4. Start chatting!

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

## Features

- Real-time WebSocket communication
- Connection status indicator
- Message history with visual distinction between sent and received messages
- Responsive design
- Support for sending messages with Enter key
- Auto-scrolling message container

## Building for Production

To create a production build:

```bash
npm run build
```

The built files will be in the `dist` directory.

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
