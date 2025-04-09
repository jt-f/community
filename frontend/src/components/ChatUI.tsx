import { useRef, useEffect, useState, createContext } from 'react';
import { AgentPanel } from './AgentPanel';
import Chat from './Chat';
import { MessageType } from '../types/message';
import { API_CONFIG, WS_CONFIG } from '../config';

// Define the structure for the context value
interface WebSocketContextValue {
  lastMessage: any | null;
  sendMessage: (message: any) => void;
  agentNameMap: Record<string, string>; // Add agent name map
}

// Create a message context to share WebSocket messages with child components
export const WebSocketContext = createContext<WebSocketContextValue>({
  lastMessage: null,
  sendMessage: () => {},
  agentNameMap: {} // Default empty map
});

interface ChatUIProps {
  userId: string;
}

export function ChatUI({ userId }: ChatUIProps) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<any | null>(null);
  const [agentNameMap, setAgentNameMap] = useState<Record<string, string>>({}); // State for agent names
  
  // Function to send a message through the WebSocket
  const sendMessage = (message: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof message === 'string' ? message : JSON.stringify(message));
      return true;
    } else {
      console.error('Cannot send message: WebSocket is not connected (readyState:', wsRef.current?.readyState, ')');
      if (wsRef.current && wsRef.current.readyState !== WebSocket.CONNECTING) {
        console.log('WebSocket not in CONNECTING state, attempting reconnect...');
        setIsConnected(false);
        scheduleReconnect();
      }
      return false;
    }
  };

  // WebSocket message handler
  const handleWebSocketMessage = (event: MessageEvent) => {
    try {
      const message = JSON.parse(event.data);
      console.log('ChatUI received message:', message);
      
      // Handle server heartbeat
      if (message.message_type === "SERVER_HEARTBEAT") {
        console.log(`Received server heartbeat at ${new Date().toISOString()}`);
        // Update the connection status in case it was incorrectly marked as disconnected
        if (!isConnected && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          console.log('Heartbeat detected active connection - updating status to connected');
          setIsConnected(true);
        }
        // Don't forward heartbeats to children to reduce noise
        return;
      }
      
      // Update agent name map if it's a status update
      if (message.message_type === MessageType.AGENT_STATUS_UPDATE && message.agents) {
        setAgentNameMap(prevMap => {
          const newMap = { ...prevMap };
          message.agents.forEach((agent: { agent_id: string; agent_name: string }) => {
            if (agent.agent_id && agent.agent_name) {
              newMap[agent.agent_id] = agent.agent_name;
            }
          });
          return newMap;
        });
      }
      
      // Set the last message to broadcast to child components
      setLastMessage(message);
      
    } catch (error) {
      console.error('Error processing WebSocket message in ChatUI:', error);
    }
  };

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
      
      // Set a connection timeout
      const connectionTimeout = setTimeout(() => {
        if (ws.readyState !== WebSocket.OPEN) {
          console.error("WebSocket connection timeout");
          ws.close();
          setIsConnected(false);
          // Attempt reconnection
          scheduleReconnect();
        }
      }, 5000);
      
      ws.onopen = () => {
        console.log('Connected to WebSocket server');
        clearTimeout(connectionTimeout);
        setIsConnected(true);
        reconnectAttemptsRef.current = 0;
        
        // Register as frontend client
        const registerMessage = {
          message_type: MessageType.REGISTER_FRONTEND,
          frontend_name: 'ChatUI',
          timestamp: new Date().toISOString()
        };
        ws.send(JSON.stringify(registerMessage));
      };
      
      ws.onmessage = handleWebSocketMessage;
      
      ws.onclose = () => {
        console.log('Disconnected from WebSocket server');
        setIsConnected(false);
        wsRef.current = null;
        
        // Use our reconnect scheduler
        scheduleReconnect();
      };
      
      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        setIsConnected(false);
      };
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      setIsConnected(false);
      scheduleReconnect();
    }
  };
  
  const scheduleReconnect = () => {
    if (reconnectAttemptsRef.current < WS_CONFIG.MAX_RECONNECT_ATTEMPTS) {
      reconnectAttemptsRef.current += 1;
      console.log(`Scheduling reconnect attempt ${reconnectAttemptsRef.current}/${WS_CONFIG.MAX_RECONNECT_ATTEMPTS} in ${WS_CONFIG.RECONNECT_INTERVAL}ms`);
      reconnectTimeoutRef.current = window.setTimeout(connectWebSocket, WS_CONFIG.RECONNECT_INTERVAL);
    } else {
      console.error('Max reconnection attempts reached. Please refresh the page.');
    }
  };
  
  // Update the WebSocket when it changes
  useEffect(() => {
    if (wsRef.current) {
      wsRef.current.onmessage = handleWebSocketMessage;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  
  // Check WebSocket connection status periodically
  useEffect(() => {
    const checkConnectionInterval = setInterval(() => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        if (isConnected) {
          console.log('Connection check: WebSocket is not open. Current state:', wsRef.current?.readyState);
          setIsConnected(false);
          if (!wsRef.current || wsRef.current.readyState === WebSocket.CLOSED) {
            console.log('WebSocket is CLOSED, attempting reconnect...');
            scheduleReconnect();
          }
        }
      } else if (!isConnected) {
        console.log('Connection check: WebSocket is open but state is not connected. Updating state.');
        setIsConnected(true);
      }
    }, 3000); // Check every 3 seconds

    return () => clearInterval(checkConnectionInterval);
  }, [isConnected]);
  
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
  
  // Return the UI with the WebSocketContext provider
  return (
    <WebSocketContext.Provider value={{ lastMessage, sendMessage, agentNameMap }}>
      <div className="chat-ui">
        <div className="chat-container">
          <Chat wsRef={wsRef} isConnected={isConnected} userId={userId} />
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
    </WebSocketContext.Provider>
  );
} 