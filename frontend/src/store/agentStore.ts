import { create } from 'zustand';

interface Agent {
  id: string;
  name: string;
  status: string;
  capabilities: string[];
  lastActivity: string;
  queueSize: number;
}

interface Message {
  id: string;
  timestamp: string;
  sender_id: string;
  receiver_id?: string;  // Optional receiver_id
  content: {
    text?: string;
    type?: string;
    [key: string]: any;
  };
  message_type: string;
  metadata?: Record<string, any>;
}

interface AgentState {
  id: string;
  name: string;
  status: string;
  queue_size: number;
  last_activity: string;
  capabilities: string[];
  metadata?: Record<string, unknown>;
}

interface AgentStore {
  socket: WebSocket | null;
  agents: Record<string, Agent>;
  selectedAgent: string | null;
  isConnected: boolean;
  messages: Message[];
  connect: () => void;
  disconnect: () => void;
  sendMessage: (message: Partial<Message>) => void;
  selectAgent: (id: string | null) => void;
  updateAgent: (id: string, data: Partial<Agent>) => void;
  removeAgent: (id: string) => void;
  addMessage: (message: Message) => void;
}

// Use secure WebSocket if the page is served over HTTPS
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const defaultPort = 8000;
// Use window.location.hostname to get the current host
const host = process.env.REACT_APP_WS_URL || `${protocol}//${window.location.hostname}:${defaultPort}/ws`;

console.log('WebSocket configuration:', {
  protocol,
  hostname: window.location.hostname,
  port: defaultPort,
  fullUrl: host
});

let reconnectTimeout: NodeJS.Timeout | null = null;
const MAX_RECONNECT_ATTEMPTS = 5;
let reconnectAttempts = 0;

// Add UUID generator function at the top of the file
function generateUUID(): string {
  // This is a simple UUID v4 generator
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

export const useAgentStore = create<AgentStore>((set, get) => ({
  socket: null,
  agents: {},
  selectedAgent: null,
  isConnected: false,
  messages: [],
  
  connect: () => {
    // Don't attempt to connect if we already have a socket
    const currentSocket = get().socket;
    if (currentSocket?.readyState === WebSocket.OPEN || 
        currentSocket?.readyState === WebSocket.CONNECTING) {
      console.log('WebSocket already connected or connecting');
      return;
    }

    // Clear any existing reconnect timeout
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
      reconnectTimeout = null;
    }

    try {
      console.log(`Attempting WebSocket connection to ${host} (attempt ${reconnectAttempts + 1}/${MAX_RECONNECT_ATTEMPTS})`);
      const socket = new WebSocket(host);
      
      // Set a connection timeout
      const connectionTimeout = setTimeout(() => {
        if (socket.readyState !== WebSocket.OPEN) {
          console.log('WebSocket connection timeout');
          socket.close();
          set({ socket: null, isConnected: false });
          
          // Try to reconnect if we haven't exceeded max attempts
          if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
            console.log(`Scheduling reconnection in ${delay}ms`);
            reconnectTimeout = setTimeout(() => get().connect(), delay);
          } else {
            console.log('Max reconnection attempts reached');
            reconnectAttempts = 0;
          }
        }
      }, 5000);
      
      socket.onopen = () => {
        clearTimeout(connectionTimeout);
        console.log('WebSocket connected successfully');
        reconnectAttempts = 0;
        set({ isConnected: true, socket });
      };
      
      socket.onclose = (event) => {
        clearTimeout(connectionTimeout);
        console.log('WebSocket connection closed:', event.code, event.reason);
        set({ isConnected: false, socket: null });
        
        // Only attempt to reconnect if it wasn't a normal closure
        if (event.code !== 1000 && event.code !== 1001) {
          if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
            console.log(`Scheduling reconnection in ${delay}ms`);
            reconnectTimeout = setTimeout(() => get().connect(), delay);
          } else {
            console.log('Max reconnection attempts reached');
            reconnectAttempts = 0;
          }
        }
      };
      
      socket.onerror = (error) => {
        console.error('WebSocket error:', error);
        clearTimeout(connectionTimeout);
        set({ isConnected: false });
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('Received WebSocket message:', data);
          
          switch (data.type) {
            case 'initial_state':
            case 'state_update':
              // Convert the incoming agent state format to our Agent interface format
              const formattedAgents: Record<string, Agent> = {};
              Object.entries(data.data).forEach(([id, agentState]: [string, any]) => {
                formattedAgents[id] = {
                  id: agentState.id,
                  name: agentState.name,
                  status: agentState.status,
                  capabilities: agentState.capabilities,
                  lastActivity: agentState.last_activity,
                  queueSize: agentState.queue_size
                };
              });
              console.log('Formatted agents:', formattedAgents);
              set({ agents: formattedAgents });
              break;
            case 'message':
              get().addMessage(data.data);
              break;
            default:
              console.warn('Unknown message type:', data.type);
          }
        } catch (error) {
          console.error('Error processing message:', error);
        }
      };

      set({ socket });
    } catch (error) {
      console.error('Error creating WebSocket connection:', error);
      set({ isConnected: false, socket: null });
      
      // Schedule reconnection
      if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        reconnectAttempts++;
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
        console.log(`Scheduling reconnection in ${delay}ms`);
        reconnectTimeout = setTimeout(() => get().connect(), delay);
      } else {
        console.log('Max reconnection attempts reached');
        reconnectAttempts = 0;
      }
    }
  },
  
  disconnect: () => {
    // Clear any pending reconnection
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
      reconnectTimeout = null;
    }
    
    const { socket } = get();
    if (socket) {
      if (socket.readyState === WebSocket.OPEN) {
        socket.close(1000, 'Normal closure');
      } else if (socket.readyState === WebSocket.CONNECTING) {
        socket.close();
      }
    }
    set({ isConnected: false, socket: null });
    reconnectAttempts = 0;
  },

  sendMessage: (message: Partial<Message>) => {
    const { socket } = get();
    if (socket?.readyState === WebSocket.OPEN) {
      const fullMessage = {
        type: 'message',
        data: {
          id: generateUUID(),
          timestamp: new Date().toISOString(),
          sender_id: message.sender_id || 'unknown',
          receiver_id: message.receiver_id,
          content: {
            text: message.content?.text || '',
            type: message.content?.type || 'text',
            ...message.content
          },
          message_type: message.message_type || 'text',
          metadata: message.metadata || {}
        }
      };
      
      console.log('Sending message:', fullMessage);
      socket.send(JSON.stringify(fullMessage));
    } else {
      console.warn('Cannot send message: WebSocket is not connected');
      // Attempt to reconnect
      get().connect();
    }
  },
  
  selectAgent: (id: string | null) => {
    set({ selectedAgent: id });
  },
  
  updateAgent: (id: string, data: Partial<Agent>) => {
    set((state) => ({
      agents: {
        ...state.agents,
        [id]: {
          ...state.agents[id],
          ...data,
          lastActivity: new Date().toISOString()
        }
      }
    }));
  },
  
  removeAgent: (id: string) => {
    set((state) => {
      const { [id]: removed, ...agents } = state.agents;
      return { agents };
    });
    
    if (get().selectedAgent === id) {
      get().selectAgent(null);
    }
  },
  
  addMessage: (message: Message) => {
    set((state) => ({
      messages: [...state.messages, message]
    }));
  }
})); 