import { useRef, useEffect, useState } from 'react';
import { AgentPanel } from './AgentPanel';
import { Chat } from './Chat';
import { MessageType } from '../types/message';
import { API_CONFIG, WS_CONFIG } from '../config';

export function ChatUI() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<number>();
  const [isConnected, setIsConnected] = useState(false);
  
  const connectWebSocket = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      const ws = new WebSocket(API_CONFIG.WS_URL);
      wsRef.current = ws;
      
      ws.onopen = () => {
        console.log('Connected to WebSocket server');
        setIsConnected(true);
        reconnectAttemptsRef.current = 0;
        
        // Register as frontend client
        const registerMessage = {
          message_type: MessageType.REGISTER_FRONTEND,
          timestamp: new Date().toISOString()
        };
        ws.send(JSON.stringify(registerMessage));
      };
      
      ws.onclose = () => {
        console.log('Disconnected from WebSocket server');
        setIsConnected(false);
        wsRef.current = null;
        
        // Attempt to reconnect if we haven't exceeded max attempts
        if (reconnectAttemptsRef.current < WS_CONFIG.MAX_RECONNECT_ATTEMPTS) {
          reconnectAttemptsRef.current += 1;
          console.log(`Attempting to reconnect (${reconnectAttemptsRef.current}/${WS_CONFIG.MAX_RECONNECT_ATTEMPTS})...`);
          reconnectTimeoutRef.current = window.setTimeout(connectWebSocket, WS_CONFIG.RECONNECT_INTERVAL);
        } else {
          console.error('Max reconnection attempts reached. Please refresh the page.');
        }
      };
      
      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setIsConnected(false);
      };
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      setIsConnected(false);
    }
  };
  
  useEffect(() => {
    connectWebSocket();

    // Cleanup on unmount
    return () => {
      if (reconnectTimeoutRef.current) {
        window.clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []); // Empty dependency array means this runs once on mount
  
  return (
    <div className="chat-ui">
      <div className="chat-container">
        <Chat wsRef={wsRef} isConnected={isConnected} />
      </div>
      <AgentPanel wsRef={wsRef} />
      
      <style>
        {`
          .chat-ui {
            display: flex;
            padding: 0 20px;
            height: calc(100vh - 120px);
            gap: 20px;
            position: relative;
          }
          
          .chat-container {
            flex: 1;
          }
        `}
      </style>
    </div>
  );
} 