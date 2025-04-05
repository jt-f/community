import { useRef, useEffect, useState } from 'react';
import { AgentPanel } from './AgentPanel';
import { Chat } from './Chat';
import { MessageType } from '../types/message';
import { API_CONFIG, WS_CONFIG } from '../config';

export function ChatUI() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  
  const connectWebSocket = () => {
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      console.log("WebSocket connection attempt already in progress or open.");
      return;
    }
    if (reconnectTimeoutRef.current) {
        window.clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
    }

    console.log(`Attempting WebSocket connection to ${API_CONFIG.WS_URL}...`);
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
      console.log("ChatUI unmounting - cleaning up WebSocket and timers.");
      // Clear any pending reconnect timeout
      if (reconnectTimeoutRef.current) {
        window.clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      
      const ws = wsRef.current;
      if (ws) {
        console.log(`Cleaning up WebSocket connection (readyState: ${ws.readyState})`);
        // Remove listeners to prevent handlers firing during/after cleanup
        ws.onopen = null;
        ws.onclose = null;
        ws.onerror = null;
        ws.onmessage = null;

        // Only call close() if the connection was actually open
        if (ws.readyState === WebSocket.OPEN) {
            console.log("Closing OPEN WebSocket connection.");
            ws.close();
        } else {
            console.log("WebSocket was not OPEN, skipping explicit close(). Browser will handle cleanup.");
        }
        
        wsRef.current = null;
      }
      setIsConnected(false); // Ensure state reflects closed connection
    };
  }, []);
  
  return (
    <div className="chat-ui">
      <div className="chat-container">
        <Chat wsRef={wsRef} isConnected={isConnected} />
      </div>
      <AgentPanel wsRef={wsRef} isConnected={isConnected} />
      
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