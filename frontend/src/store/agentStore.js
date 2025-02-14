import { create } from 'zustand';

// Get WebSocket URL from environment or default to localhost
const WS_URL = 'ws://172.19.36.55:8000/ws'; 
const RECONNECT_INTERVAL = 2000; // 2 seconds
const CONNECTION_TIMEOUT = 5000; // 5 seconds

const useAgentStore = create((set, get) => ({
  agents: {},
  messages: [],
  connected: false,
  socket: null,
  error: null,
  reconnectAttempts: 0,
  maxReconnectAttempts: 10,
  connectionTimer: null,

  addMessage: (message) => {
    set((state) => ({
      messages: [...state.messages.slice(-19), message], // Keep last 20 messages
    }));
  },

  connect: () => {
    const state = get();
    
    // Clear any existing connection timer
    if (state.connectionTimer) {
      clearTimeout(state.connectionTimer);
    }

    if (state.socket?.readyState === WebSocket.OPEN) {
      console.log('WebSocket connection already exists and is open');
      return;
    }

    // Close existing socket if it exists
    if (state.socket) {
      console.log('Closing existing socket before reconnecting');
      state.socket.close();
    }

    console.log('Attempting to connect to WebSocket server at:', WS_URL);
    const socket = new WebSocket(WS_URL);
    set({ socket }); // Store socket reference immediately

    // Set connection timeout
    const connectionTimer = setTimeout(() => {
      if (socket.readyState !== WebSocket.OPEN) {
        console.error('Connection timeout - closing socket');
        socket.close();
        set({ 
          error: 'Connection timeout',
          connected: false,
          socket: null
        });
      }
    }, CONNECTION_TIMEOUT);

    set({ connectionTimer });
    
    socket.onopen = () => {
      console.log('WebSocket connection established successfully');
      clearTimeout(connectionTimer);
      set({ 
        connected: true, 
        error: null,
        reconnectAttempts: 0,
        connectionTimer: null
      });
    };

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log('Received WebSocket message:', message);
        
        switch (message.type) {
          case 'state_update':
            console.log('Processing state update:', message.data);
            set({ agents: message.data });
            break;
          case 'message':
            console.log('Processing message:', message.data);
            get().addMessage(message.data);
            break;
          case 'server_message':
            console.log('Server message:', message.data.message);
            break;
          case 'message_receipt':
            console.log('Message receipt:', message.data);
            break;
          default:
            console.warn('Unknown message type:', message.type);
        }
      } catch (err) {
        console.error('Failed to parse message:', err);
        console.error('Raw message data:', event.data);
      }
    };

    socket.onerror = (error) => {
      console.error('WebSocket error occurred:', error);
      set({ error: 'WebSocket connection error' });
    };

    socket.onclose = (event) => {
      console.log('WebSocket connection closed. Code:', event.code, 'Reason:', event.reason);
      clearTimeout(state.connectionTimer);
      
      set(state => ({ 
        connected: false, 
        socket: null,
        connectionTimer: null,
        reconnectAttempts: state.reconnectAttempts + 1
      }));

      // Attempt to reconnect if we haven't exceeded max attempts
      const currentState = get();
      if (currentState.reconnectAttempts < currentState.maxReconnectAttempts) {
        console.log(`Attempting to reconnect... (Attempt ${currentState.reconnectAttempts + 1}/${currentState.maxReconnectAttempts})`);
        setTimeout(() => {
          if (!get().connected) {
            get().connect();
          }
        }, RECONNECT_INTERVAL);
      } else {
        console.error('Max reconnection attempts reached');
        set({ error: 'Failed to maintain WebSocket connection' });
      }
    };
  },

  disconnect: () => {
    const state = get();
    if (state.connectionTimer) {
      clearTimeout(state.connectionTimer);
    }
    if (state.socket) {
      console.log('Closing WebSocket connection');
      state.socket.close();
    }
    set({ 
      socket: null, 
      connected: false,
      reconnectAttempts: 0,
      connectionTimer: null,
      error: null
    });
  },

  // Reset connection
  resetConnection: () => {
    const state = get();
    state.disconnect();
    set({ 
      reconnectAttempts: 0,
      error: null
    });
    get().connect();
  },

  getAgentById: (id) => {
    return get().agents[id];
  },

  getAgentsByStatus: (status) => {
    const agents = get().agents;
    return Object.values(agents).filter(agent => agent.status === status);
  },

  getTotalQueueSize: () => {
    const agents = get().agents;
    return Object.values(agents).reduce((sum, agent) => sum + agent.queue_size, 0);
  },
}));

export { useAgentStore }; 