import { useRef } from 'react';
import { AgentPanel } from './AgentPanel';
import { Chat } from './Chat';

export function ChatUI() {
  // Shared WebSocket reference
  const wsRef = useRef<WebSocket | null>(null);
  
  // Connect to the WebSocket
  if (!wsRef.current) {
    const ws = new WebSocket('ws://localhost:8765/ws');
    wsRef.current = ws;
    
    ws.onopen = () => {
      console.log('Connected to WebSocket server');
    };
    
    ws.onclose = () => {
      console.log('Disconnected from WebSocket server');
      wsRef.current = null;
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }
  
  return (
    <div className="chat-ui">
      <div className="chat-container">
        <Chat wsRef={wsRef} />
      </div>
      <AgentPanel wsRef={wsRef} />
      
      <style>
        {`
          .chat-ui {
            display: flex;
            padding: 0 20px;
            height: calc(100vh - 120px);
            gap: 20px;
          }
          
          .chat-container {
            flex: 1;
          }
        `}
      </style>
    </div>
  );
} 