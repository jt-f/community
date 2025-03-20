import { useEffect, useCallback } from 'react';
import { create } from 'zustand';

interface AgentState {
  id: string;
  name: string;
  status: string;
  queue_size: number;
  last_activity: string;
  capabilities: string[];
  metadata?: Record<string, unknown>;
}

interface MessageContent {
  text?: string;
  status?: string;
  insights?: string[];
  type?: string;
  timestamp?: string;
  [key: string]: any;
}

interface Message {
  id: string;
  timestamp: string;
  sender_id: string;
  content: MessageContent;
  message_type: string;
  metadata?: Record<string, unknown>;
}

interface MessageWSData {
  type: 'message';
  data: Message;
}

interface StateWSData {
  type: 'initial_state' | 'state_update';
  data: Record<string, AgentState>;
}

type WebSocketMessageData = MessageWSData | StateWSData;

interface WebSocketState {
  socket: WebSocket | null;
  connected: boolean;
  agents: Record<string, AgentState>;
  messages: Message[];
  connect: () => void;
  disconnect: () => void;
  sendMessage: (message: Partial<Message>) => Promise<void>;
}

const WS_URL = process.env.REACT_APP_WS_URL || 'ws://172.19.36.55:8000/ws';

export const useWebSocketStore = create<WebSocketState>((set, get) => ({
  socket: null,
  connected: false,
  agents: {},
  messages: [],

  connect: () => {
    if (get().socket?.readyState === WebSocket.OPEN) return;

    const socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      console.info('WebSocket connected');
      set({ socket, connected: true });
    };

    socket.onclose = () => {
      console.info('WebSocket disconnected');
      set({ socket: null, connected: false });
      // Attempt to reconnect after 5 seconds
      setTimeout(() => get().connect(), 5000);
    };

    socket.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    socket.onmessage = (event) => {
      try {
        const receiveTime = new Date().getTime();
        console.log(`WebSocket message received at ${receiveTime}ms:`, event.data);
        
        const data = JSON.parse(event.data) as WebSocketMessageData;
        
        switch (data.type) {
          case 'initial_state':
          case 'state_update':
            set({ agents: data.data });
            break;
          
          case 'message':
            set((state) => ({
              messages: [...state.messages, data.data]
            }));
            break;
          
          default:
            const _exhaustiveCheck: never = data;
            console.warn('Unknown message type:', _exhaustiveCheck);
        }
      } catch (error) {
        console.error('(useWebSocket) Error processing message:', error);
      }
    };

    set({ socket });
  },

  disconnect: () => {
    const { socket } = get();
    if (socket) {
      socket.close();
      set({ socket: null, connected: false });
    }
  },

  sendMessage: async (message: Partial<Message>) => {
    const { socket } = get();
    if (socket?.readyState === WebSocket.OPEN) {
      const fullMessage: MessageWSData = {
        type: 'message',
        data: {
          id: crypto.randomUUID(),
          timestamp: new Date().toISOString(),
          sender_id: message.sender_id || 'unknown',
          content: message.content || {},
          message_type: message.message_type || 'text',
          metadata: message.metadata
        }
      };
      socket.send(JSON.stringify(fullMessage));
      console.log(`WebSocket message sent to backend:`, fullMessage);
    } else {
      throw new Error('WebSocket not connected');
    }
  }
}));

export const useWebSocket = () => {
  const { connect, disconnect, connected, agents, messages, sendMessage } = useWebSocketStore();

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  const send = useCallback(async (message: Partial<Message>) => {
    await sendMessage(message);
  }, [sendMessage]);

  return {
    connected,
    agents,
    messages,
    send
  };
}; 