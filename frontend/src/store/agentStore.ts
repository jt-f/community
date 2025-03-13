import { create } from 'zustand';
import { WebSocketMessage } from '../types/WebSocketMessage';

interface Agent {
  id: string;
  name: string;
  type: string;
  status: 'active' | 'busy' | 'offline';
  capabilities: string[];
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
  type?: string;  // Add this field for 'incoming' or 'outgoing'
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
  sendMessage: (content: string, agentId: string, addToUI: boolean) => void;
  selectAgent: (id: string | null) => void;
  updateAgent: (id: string, data: Partial<Agent>) => void;
  removeAgent: (id: string) => void;
  addMessage: (message: Message) => void;
  addAgent: (agent: Agent) => void;
}

// Use secure WebSocket if the page is served over HTTPS
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const defaultPort = 8000;

console.log('WebSocket configuration:', {
  protocol,
  hostname: window.location.hostname,
  port: defaultPort,
  fullUrl: process.env.REACT_APP_WS_URL || `${protocol}//${window.location.hostname}:${defaultPort}/ws`
});

export const useAgentStore = create<AgentStore>((set, get) => {
  let socket: WebSocket | null = null;

  return {
    socket: null,
    agents: {},
    selectedAgent: null,
    isConnected: false,
    messages: [],
    
    connect: () => {
      if (socket !== null) return;
      
      // Simplified WebSocket URL construction
      const wsUrl = process.env.NODE_ENV === 'development' 
        ? 'ws://localhost:8000/ws' 
        : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;
      
      console.log('Connecting to WebSocket at:', wsUrl);
      socket = new WebSocket(wsUrl);
      
      socket.onopen = () => {
        console.log('WebSocket connected');
        set({ isConnected: true });
      };
      
      socket.onclose = () => {
        console.log('WebSocket disconnected');
        set({ isConnected: false });
        socket = null;
      };
      
      socket.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
      
      socket.onmessage = (event) => {
        try {
          console.log('WebSocket message received:', event.data);
          const data = JSON.parse(event.data) as WebSocketMessage;
          
          if (data.type === 'agent_list') {
            console.log('Received agent list:', data.data);
            // Update agent list
            const agentMap: Record<string, Agent> = {};
            
            // Add null check for data.data.agents
            if (data.data && data.data.agents && Array.isArray(data.data.agents)) {
              data.data.agents.forEach((agent: any) => {
                console.log('Processing agent:', agent);
                agentMap[agent.id] = {
                  id: agent.id,
                  name: agent.name,
                  // Ensure type is lowercase for consistent comparison
                  type: (agent.type || 'unknown').toLowerCase(),
                  status: agent.status || 'active',
                  capabilities: agent.capabilities || [],
                };
              });
              console.log('Setting agents:', agentMap);
              set({ agents: agentMap });
            }
          } else if (data.type === 'message') {
            // Handle incoming messages
            if (data.data) {
              const messageData = data.data;
              const newMessage: Message = {
                id: messageData.id || Math.random().toString(36).substring(2, 9),
                sender_id: messageData.sender_id,
                receiver_id: messageData.receiver_id,
                content: messageData.content,
                timestamp: messageData.timestamp || new Date().toISOString(),
                message_type: messageData.message_type || 'text',
                type: 'incoming'
              };
              
              set((state) => ({
                messages: [...state.messages, newMessage]
              }));
            }
          }
          
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };
    },
    
    disconnect: () => {
      if (socket) {
        socket.close();
        socket = null;
        set({ isConnected: false });
      }
    },
    
    sendMessage: (content: string, agentId: string, addToUI: boolean = true) => {
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        console.error('WebSocket not connected');
        return;
      }
      
      const userId = localStorage.getItem('userId') || 'user-' + Math.random().toString(36).substring(2, 9);
      localStorage.setItem('userId', userId);
      
      const message = {
        type: 'message',
        data: {
          sender_id: userId,
          receiver_id: agentId,
          content: {
            text: content,
            timestamp: new Date().toISOString()
          },
          message_type: 'text'
        }
      };
      
      console.log('Sending message to agent:', agentId);
      socket.send(JSON.stringify(message));
      
      // Add the message to the local state only if addToUI is true
      if (addToUI) {
        const newMessage: Message = {
          id: Math.random().toString(36).substring(2, 9),
          sender_id: userId,
          receiver_id: agentId,
          content: { text: content },
          timestamp: new Date().toISOString(),
          type: 'outgoing',
          message_type: 'text'
        };
        
        set((state) => ({
          messages: [...state.messages, newMessage]
        }));
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
    },
    
    addAgent: (agent) => {
      set((state) => ({
        agents: {
          ...state.agents,
          [agent.id]: agent
        }
      }));
    }
  };
}); 