import { create } from 'zustand';
import { WebSocketMessage } from '../types/WebSocketMessage';

interface Agent {
  id: string;
  name: string;
  type: string;
  status: 'active' | 'busy' | 'offline';
  capabilities: string[];
  model?: string;
  provider?: string;
}

interface Message {
  id?: string;
  message_id?: string;
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
  // Add fields for nested message structure
  message?: {
    sender_id?: string;
    receiver_id?: string;
    content?: any;
    timestamp?: string;
    message_id?: string;
  };
  data?: {
    message?: {
      sender_id?: string;
      receiver_id?: string;
      content?: any;
      timestamp?: string;
      message_id?: string;
    };
    timestamp?: string;
    sender_id?: string;
    receiver_id?: string;
    content?: any;
  };
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
  processedMessageIds: Set<string>;
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

// Add a function to normalize message structure
const normalizeMessage = (message: any): Message => {
  console.log('Normalizing message:', message);
  
  // If it's already in the expected format with sender_id and content
  if (message.sender_id && (message.content !== undefined)) {
    return {
      id: message.id || message.message_id || Math.random().toString(36).substring(2, 9),
      message_id: message.message_id || message.id || Math.random().toString(36).substring(2, 9),
      sender_id: message.sender_id,
      receiver_id: message.receiver_id,
      content: message.content,
      timestamp: message.timestamp || new Date().toISOString(),
      message_type: message.message_type || 'text',
      type: message.type || 'incoming'
    };
  }
  
  // If it's a WebSocket message with data.message structure
  if (message.type === 'message' && message.data && message.data.message) {
    const wsMessage = message.data.message;
    return {
      id: wsMessage.message_id || wsMessage.id || message.id || Math.random().toString(36).substring(2, 9),
      message_id: wsMessage.message_id || wsMessage.id || message.id || Math.random().toString(36).substring(2, 9),
      sender_id: wsMessage.sender_id || message.data.sender_id || 'unknown',
      receiver_id: wsMessage.receiver_id || message.data.receiver_id,
      content: wsMessage.content || message.data.content || { text: 'No content available' },
      timestamp: wsMessage.timestamp || message.data.timestamp || new Date().toISOString(),
      message_type: wsMessage.message_type || 'text',
      type: message.type || 'incoming'
    };
  }
  
  // If it's a WebSocket message with direct data structure
  if (message.type === 'message' && message.data) {
    return {
      id: message.data.message_id || message.data.id || message.id || Math.random().toString(36).substring(2, 9),
      message_id: message.data.message_id || message.data.id || message.id || Math.random().toString(36).substring(2, 9),
      sender_id: message.data.sender_id || 'unknown',
      receiver_id: message.data.receiver_id,
      content: message.data.content || { text: 'No content available' },
      timestamp: message.data.timestamp || new Date().toISOString(),
      message_type: message.data.message_type || 'text',
      type: message.type || 'incoming'
    };
  }
  
  // If it's a nested message structure
  if (message.message) {
    return {
      id: message.message.message_id || message.message.id || message.id || Math.random().toString(36).substring(2, 9),
      message_id: message.message.message_id || message.message.id || message.id || Math.random().toString(36).substring(2, 9),
      sender_id: message.message.sender_id || 'unknown',
      receiver_id: message.message.receiver_id,
      content: message.message.content || { text: 'No content available' },
      timestamp: message.message.timestamp || message.timestamp || new Date().toISOString(),
      message_type: message.message.message_type || 'text',
      type: message.type || 'incoming'
    };
  }
  
  // If we can't normalize it, return as is with some defaults
  return {
    id: message.id || message.message_id || Math.random().toString(36).substring(2, 9),
    message_id: message.message_id || message.id || Math.random().toString(36).substring(2, 9),
    sender_id: message.sender_id || 'unknown',
    receiver_id: message.receiver_id,
    content: message.content || { text: 'No content available' },
    timestamp: message.timestamp || new Date().toISOString(),
    message_type: message.message_type || 'text',
    type: message.type || 'incoming'
  };
};

export const useAgentStore = create<AgentStore>((set, get) => {
  let socket: WebSocket | null = null;

  return {
    socket: null,
    agents: {},
    selectedAgent: null,
    isConnected: false,
    messages: [],
    processedMessageIds: new Set<string>(),
    
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
                  type: (agent.type || 'unknown').toLowerCase(),
                  status: agent.status || 'active',
                  capabilities: agent.capabilities || [],
                  model: agent.model || undefined,
                  provider: agent.provider || undefined
                };
              });
              console.log('Setting agents:', agentMap);
              set({ agents: agentMap });
            }
          } else if (data.type === 'message') {
            // Handle incoming messages
            console.log('Received message data:', data);
            
            // Use the normalizeMessage function to handle different message formats
            const normalizedMessage = normalizeMessage(data);
            console.log('Normalized message:', normalizedMessage);
            
            // Check if we've already processed this message
            const messageId = normalizedMessage.id;
            if (messageId && get().processedMessageIds.has(messageId)) {
              console.log('Skipping duplicate message with ID:', messageId);
              return;
            }
            
            // Add message ID to processed set
            if (messageId) {
              get().processedMessageIds.add(messageId);
            }
            
            // Add the normalized message to the store
            set((state) => ({
              messages: [...state.messages, normalizedMessage]
            }));
          } else if (data.type === 'state_update') {
            // Handle state updates
            console.log('Received state update:', data.data);
            
            if (data.data) {
              const agentMap: Record<string, Agent> = {};
              
              // Process each agent in the state update
              Object.entries(data.data).forEach(([agentId, agentState]: [string, any]) => {
                console.log('Processing agent state:', agentId, agentState);
                
                // Convert agent state to agent object
                agentMap[agentId] = {
                  id: agentId,
                  name: agentState.name || 'Unknown Agent',
                  type: (agentState.type || 'unknown').toLowerCase(),
                  status: agentState.status || 'active',
                  capabilities: agentState.capabilities || [],
                  model: agentState.model,
                  provider: agentState.provider
                };
              });
              
              console.log('Setting updated agents:', agentMap);
              set({ agents: agentMap });
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
      
      const messageId = Math.random().toString(36).substring(2, 9);
      
      const message = {
        type: 'message',
        data: {
          message_id: messageId,
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
          id: messageId,
          sender_id: userId,
          receiver_id: agentId,
          content: { text: content },
          timestamp: new Date().toISOString(),
          type: 'outgoing',
          message_type: 'text'
        };
        
        // Add message ID to processed set
        get().processedMessageIds.add(messageId);
        
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
    
    addMessage: (message) => {
      console.log('Adding message to store:', message);
      const normalizedMessage = normalizeMessage(message);
      console.log('Normalized message:', normalizedMessage);
      
      // Check if we've already processed this message
      const messageId = normalizedMessage.id;
      if (messageId && get().processedMessageIds.has(messageId)) {
        console.log('Skipping duplicate message with ID:', messageId);
        return;
      }
      
      // Add message ID to processed set
      if (messageId) {
        get().processedMessageIds.add(messageId);
      }
      
      set((state) => ({
        messages: [...state.messages, normalizedMessage]
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