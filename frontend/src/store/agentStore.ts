import { create } from 'zustand';
import { WebSocketMessage } from '../types/WebSocketMessage';
import { getAgentName } from '../utils/agentUtils';
import { useMessageStore } from './messageStore';
import { generateShortId } from '../utils/idGenerator';

interface Agent {
  id: string;
  name: string;
  type: string;
  status: 'idle' | 'responding' | 'thinking';
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
  sendMessage: (content: string, agentId: string, addToUI: boolean, messageId?: string, inReplyTo?: string) => void;
  selectAgent: (id: string | null) => void;
  updateAgent: (id: string, data: Partial<Agent>) => void;
  removeAgent: (id: string) => void;
  addMessage: (message: Message) => void;
  addAgent: (agent: Agent) => void;
}

// Use secure WebSocket if the page is served over HTTPS
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const defaultPort = 8000;

// Add timestamp utility at the top of the file
const getTimestamp = () => new Date().toISOString();

console.log(`[${getTimestamp()}] WebSocket configuration:`, {
  protocol,
  hostname: window.location.hostname,
  port: defaultPort,
  fullUrl: process.env.REACT_APP_WS_URL || `${protocol}//${window.location.hostname}:${defaultPort}/ws`
});

// Add a function to normalize message structure
const normalizeMessage = (message: any): Message => {

  // If it's already in the expected format with sender_id and content
  if (message.sender_id && (message.content !== undefined)) {
    return {
      id: message.id || message.message_id || generateShortId(),
      message_id: message.message_id || message.id || generateShortId(),
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
      id: wsMessage.message_id || wsMessage.id || message.id || generateShortId(),
      message_id: wsMessage.message_id || wsMessage.id || message.id || generateShortId(),
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
      id: message.data.message_id || message.data.id || message.id || generateShortId(),
      message_id: message.data.message_id || message.data.id || message.id || generateShortId(),
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
      id: message.message.message_id || message.message.id || message.id || generateShortId(),
      message_id: message.message.message_id || message.message.id || message.id || generateShortId(),
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
    id: message.id || message.message_id || generateShortId(),
    message_id: message.message_id || message.id || generateShortId(),
    sender_id: message.sender_id || 'unknown',
    receiver_id: message.receiver_id,
    content: message.content || { text: 'No content available' },
    timestamp: message.timestamp || new Date().toISOString(),
    message_type: message.message_type || 'text',
    type: message.type || 'incoming'
  };
};

// Helper to convert from agentStore message format to messageStore format
const convertToMessageStoreFormat = (message: Message) => {
  return {
    message_id: message.message_id || message.id || '',
    timestamp: message.timestamp,
    sender_id: message.sender_id,
    receiver_id: message.receiver_id,
    in_reply_to: message.content?.in_reply_to || message.metadata?.in_reply_to,
    content: message.content,
    message_type: message.message_type,
    metadata: message.metadata || {},
    is_outgoing: message.type === 'outgoing'
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
        console.log(`[${getTimestamp()}] WebSocket connected`);
        set({ isConnected: true });
      };
      
      socket.onclose = () => {
        console.log(`[${getTimestamp()}] WebSocket disconnected`);
        set({ isConnected: false });
        socket = null;
      };
      
      socket.onerror = (error) => {
        console.error(`[${getTimestamp()}] WebSocket error:`, error);
      };
      
      socket.onmessage = (event) => {
        try {
          const receiveTime = new Date().getTime();
          console.log(`[${getTimestamp()}] WebSocket message received at ${receiveTime}ms:`, event.data);
          
          // Parse the message and extract its timestamp
          const data = JSON.parse(event.data) as WebSocketMessage;
          const messageTimestamp = data.data?.timestamp ? new Date(data.data.timestamp).getTime() : null;
          
          if (messageTimestamp) {
            const delay = receiveTime - messageTimestamp;
            console.log(`[${getTimestamp()}] Message delay: ${delay}ms (Server timestamp: ${messageTimestamp}ms)`);
          }
          
          if (data.type === 'agent_list') {
            console.log(`[${getTimestamp()}] Received agent list:`, data.data);
            // Update agent list
            const agentMap: Record<string, Agent> = {};
            
            // Add null check for data.data.agents
            if (data.data && data.data.agents && Array.isArray(data.data.agents)) {
              data.data.agents.forEach((agent: any) => {
                agentMap[agent.id] = {
                  id: agent.id,
                  name: agent.name,
                  type: (agent.type || 'unknown').toLowerCase(),
                  status: agent.status || 'idle',
                  capabilities: agent.capabilities || [],
                  model: agent.model || undefined,
                  provider: agent.provider || undefined
                };
              });
              set({ agents: agentMap });
            }
          } else if (data.type === 'message') {
            // Use the normalizeMessage function to handle different message formats
            const normalizedMessage = normalizeMessage(data);
            
            // Check if we've already processed this message
            const messageId = normalizedMessage.id || normalizedMessage.message_id;
            if (messageId && get().processedMessageIds.has(messageId)) {
              console.log('Skipping duplicate message with ID:', messageId);
              return;
            }
            
            // Add message ID to processed set
            if (messageId) {
              get().processedMessageIds.add(messageId);
            }
            
            // Add the normalized message to the agentStore
            set((state) => ({
              messages: [...state.messages, normalizedMessage]
            }));
            
            // Also add to messageStore
            const messageStoreFormat = convertToMessageStoreFormat(normalizedMessage);
            useMessageStore.getState().addMessage(messageStoreFormat);
          } else if (data.type === 'state_update') {
            // Handle state updates
            console.log(`[${getTimestamp()}] Received state update:`, data.data);
            
            if (data.data) {
              // Get current agents to preserve any that aren't in the update
              const currentAgents = get().agents;
              const updatedAgents: Record<string, Agent> = { ...currentAgents };
              
              // Process each agent in the state update
              Object.entries(data.data).forEach(([agentId, agentState]: [string, any]) => {
                // Convert agent state to agent object
                updatedAgents[agentId] = {
                  id: agentId,
                  name: agentState.name || 'Unknown Agent',
                  type: (agentState.type || 'unknown').toLowerCase(),
                  status: agentState.status || 'idle',
                  capabilities: agentState.capabilities || [],
                  model: agentState.model,
                  provider: agentState.provider
                };
              });
              
              console.log(`[${getTimestamp()}] Setting updated agents:`, updatedAgents);
              set({ agents: updatedAgents });
            }
          }
          
        } catch (error) {
          console.error(`[${getTimestamp()}] Error parsing WebSocket message:`, error);
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
    
    sendMessage: async (message: string, receiverId: string, addToUI: boolean = true, messageId?: string, in_reply_to?: string) => {
      if (!socket || !get().isConnected) {
        console.error('WebSocket not connected');
        return;
      }

      // Get the human agent ID from the agents list
      const humanAgent = Object.values(get().agents).find(agent => agent.type.toLowerCase() === 'human');
      if (!humanAgent) {
        console.error('No human agent found');
        return;
      }

      const messageData = {
        type: 'message',
        data: {
          message_id: messageId || generateShortId(),
          sender_id: humanAgent.id,
          receiver_id: receiverId,
          content: { text: message },
          message_type: 'text',
          in_reply_to: in_reply_to
        }
      };
      
      console.log(`[${getTimestamp()}] Sending message to agent:`, getAgentName(receiverId, get().agents));
      socket.send(JSON.stringify(messageData));
      
      // Add the message to the local state only if addToUI is true
      if (addToUI) {
        const newMessage: Message = {
          id: messageData.data.message_id,
          message_id: messageData.data.message_id,
          sender_id: messageData.data.sender_id,
          receiver_id: messageData.data.receiver_id,
          content: messageData.data.content,
          timestamp: new Date().toISOString(),
          type: 'outgoing',
          message_type: messageData.data.message_type
        };
        
        // Add message ID to processed set
        get().processedMessageIds.add(messageData.data.message_id);
        
        // Also add to messageStore
        const messageStoreFormat = convertToMessageStoreFormat(newMessage);
        useMessageStore.getState().addMessage(messageStoreFormat);
        
        // Update the agent status to 'thinking' when a message is sent to it
        const currentAgents = get().agents;
        if (currentAgents[receiverId]) {
          set((state) => ({
            messages: [...state.messages, newMessage],
            agents: {
              ...state.agents,
              [receiverId]: {
                ...state.agents[receiverId],
                status: 'thinking'
              }
            }
          }));
        } else {
          // If the agent doesn't exist in the store, just add the message without updating agents
          set((state) => ({
            messages: [...state.messages, newMessage]
          }));
          
          // Log a warning that the agent wasn't found
          console.warn(`[${getTimestamp()}] Warning: Agent ${receiverId} not found in store when sending message`);
        }
      } else {
        // Even if we don't add to UI, we should still add message ID to processed set
        // and update agent status
        get().processedMessageIds.add(messageData.data.message_id);
        
        // Update the agent status to 'thinking' when a message is sent to it
        const currentAgents = get().agents;
        if (currentAgents[receiverId]) {
          set((state) => ({
            agents: {
              ...state.agents,
              [receiverId]: {
                ...state.agents[receiverId],
                status: 'thinking'
              }
            }
          }));
        }
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
      console.log(`[${getTimestamp()}] Adding message to store:`, message);
      const normalizedMessage = normalizeMessage(message);
      console.log(`[${getTimestamp()}] Normalized message:`, normalizedMessage);
      
      // Check if we've already processed this message
      const messageId = normalizedMessage.id || normalizedMessage.message_id;
      if (messageId && get().processedMessageIds.has(messageId)) {
        console.log(`[${getTimestamp()}] Skipping duplicate message with ID:`, messageId);
        return;
      }
      
      // Add message ID to processed set
      if (messageId) {
        get().processedMessageIds.add(messageId);
      }
      
      // Add to agentStore
      set((state) => ({
        messages: [...state.messages, normalizedMessage]
      }));
      
      // Also add to messageStore
      const messageStoreFormat = convertToMessageStoreFormat(normalizedMessage);
      useMessageStore.getState().addMessage(messageStoreFormat);
    },
    
    addAgent: (agent) => {
      console.log(`[${getTimestamp()}] Adding agent to store:`, agent);
      
      // Ensure the agent has all required fields
      const completeAgent: Agent = {
        id: agent.id,
        name: agent.name || 'Unknown Agent',
        type: (agent.type || 'unknown').toLowerCase(),
        status: agent.status || 'idle',
        capabilities: agent.capabilities || [],
        model: agent.model,
        provider: agent.provider
      };
      
      set((state) => ({
        agents: {
          ...state.agents,
          [agent.id]: completeAgent
        }
      }));
      
      console.log(`[${getTimestamp()}] Updated agents store:`, get().agents);
    }
  };
}); 