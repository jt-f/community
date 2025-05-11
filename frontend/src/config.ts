// API Configuration
export const API_CONFIG = {
  WS_URL: import.meta.env.VITE_WS_URL || 'ws://localhost:8765/ws',
  API_URL: import.meta.env.VITE_API_URL || 'http://localhost:8765'
};

// WebSocket Configuration
export const WS_CONFIG = {
  RECONNECT_INTERVAL: 5000, // 5 seconds
  MAX_RECONNECT_ATTEMPTS: 5
}; 