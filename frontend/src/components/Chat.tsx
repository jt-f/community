import { useState, useEffect, useRef } from 'react';
import { ChatMessage, MessageType, createMessage } from '../types/message';

interface ChatProps {
  wsRef: React.MutableRefObject<WebSocket | null>;
  isConnected: boolean;
}

interface MessageWithAnimation extends ChatMessage {
  isNew?: boolean;
  animationPhase?: 'fadeIn' | 'vibrate' | null;
}

export function Chat({ wsRef, isConnected }: ChatProps) {
  const [messages, setMessages] = useState<MessageWithAnimation[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const userId = useRef(`user_${Math.random().toString(36).substring(2, 11)}`);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Only proceed if the WebSocket is connected
    if (!isConnected || !wsRef.current) {
      // Optional: Clean up any potential stale listeners if isConnected becomes false
      // This might not be strictly necessary if the parent correctly nullifies wsRef.current on disconnect
      // but can add robustness.
      // if (wsRef.current) { wsRef.current.onmessage = null; }
      return;
    }

    const ws = wsRef.current; // We know wsRef.current is not null here

    // Define the message handler
    const handleMessage = (event: MessageEvent) => {
      console.log("Chat.tsx: Received raw message data:", event.data); // Log raw data
      try {
        const data = JSON.parse(event.data);

        // Use MessageType enum for comparison
        if (data.message_type !== MessageType.AGENT_STATUS_UPDATE) {
          const message = data as ChatMessage;
          const messageWithAnimation: MessageWithAnimation = {
            ...message,
            isNew: true,
            animationPhase: 'fadeIn'
          };
          setMessages(prev => [...prev, messageWithAnimation]);
        } else {
          // Optionally log skipped status updates for debugging
          // console.log("Chat.tsx: Skipped AGENT_STATUS_UPDATE message.");
        }
      } catch (error) {
        console.error('Chat.tsx: Failed to parse message:', error);
      }
    };

    // Attach the listener
    ws.addEventListener('message', handleMessage);
    console.log("Chat.tsx: Attached message listener."); // Confirm attachment

    // Clean up the listener when the component unmounts or isConnected changes
    return () => {
      ws.removeEventListener('message', handleMessage);
      console.log("Chat.tsx: Removed message listener."); // Confirm removal
    };
    // Depend on the connection status and the ref object itself
  }, [isConnected, wsRef]);

  // Auto-scroll when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = () => {
    if (inputMessage.trim() && wsRef.current?.readyState === WebSocket.OPEN) {
      const message = createMessage(
        userId.current,
        'broker',
        inputMessage,
        MessageType.TEXT
      );
      
      // Add animation status to sent messages
      const messageWithAnimation: MessageWithAnimation = {
        ...message,
        isNew: true,
        animationPhase: 'fadeIn' // Start with fade in
      };
      
      wsRef.current.send(JSON.stringify(message));
      setMessages(prev => [...prev, messageWithAnimation]);
      setInputMessage('');
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      sendMessage();
    }
  };

  // Handle fade-in animation completion
  const handleFadeInComplete = (index: number) => {
    // After fade-in is complete, start vibration
    setMessages(msgs => 
      msgs.map((m, i) => 
        i === index ? { ...m, animationPhase: 'vibrate' } : m
      )
    );
    
    // After vibration completes, clear animation status
    setTimeout(() => {
      setMessages(msgs => 
        msgs.map((m, i) => 
          i === index ? { ...m, isNew: false, animationPhase: null } : m
        )
      );
    }, 500); // Duration of vibration animation
  };

  return (
    <div className="chat-container">
      <div className="chat-header">
        <div className="header-title">
          <span className="header-icon">⚡</span>
          <h3>SECURE COMMUNICATIONS</h3>
        </div>
        <div className="connection-status">
          <div className={`status-indicator ${isConnected ? 'connected' : 'disconnected'}`}></div>
          <span className="status-text">{isConnected ? 'CONNECTED' : 'DISCONNECTED'}</span>
        </div>
      </div>
      <div className="messages-container">
        <div className="messages-header">
          <div className="channel-info">
            <span className="channel-label">CHANNEL:</span>
            <span className="channel-value">MAIN-01</span>
          </div>
          <div className="timestamp">
            <span>{new Date().toISOString().split('T')[0]} • {new Date().toLocaleTimeString()}</span>
          </div>
        </div>
        <div className="messages">
          {messages.map((message, index) => (
            <div
              key={message.message_id}
              className={`message 
                ${message.sender_id === userId.current ? 'sent' : 'received'} 
                ${message.animationPhase === 'fadeIn' ? 'fade-in' : ''}
                ${message.animationPhase === 'vibrate' ? 'vibrate' : ''}
                ${message.message_type === MessageType.ERROR ? 'error' : ''}`}
              onAnimationEnd={() => {
                if (message.animationPhase === 'fadeIn') {
                  handleFadeInComplete(index);
                }
              }}
            >
              <div className="message-header">
                <span className="sender">{message.sender_id}</span>
                <span className="timestamp">{message.send_timestamp}</span>
              </div>
              <div className="message-content">
                {message.text_payload}
              </div>
              {message.message_type === MessageType.REPLY && (
                <div className="message-footer reply">
                  <span className="message-id">ID: {message.message_id.substring(0, 8)}</span>
                  <span className="reply-to">↩ {message.in_reply_to_message_id?.substring(0, 8)}</span>
                </div>
              )}
              {message.message_type === MessageType.TEXT && (
                <div className="message-footer">
                  <span className="message-id">ID: {message.message_id.substring(0, 8)}</span>
                </div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>
      <div className="input-container">
        <input
          type="text"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyUp={handleKeyPress}
          placeholder="Enter message..."
          disabled={!isConnected}
        />
        <button onClick={sendMessage} disabled={!isConnected}>
          TRANSMIT
        </button>
      </div>
      <style>
        {`
          .chat-container {
            width: 100%;
            margin: 0;
            padding: 0;
            border: 1px solid var(--color-border-strong);
            border-radius: 4px;
            background-color: var(--color-surface);
            display: flex;
            flex-direction: column;
            height: 100%;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
            overflow: hidden;
            position: relative;
          }
          
          /* Outer glow effect */
          .chat-container::before {
            content: '';
            position: absolute;
            top: -1px;
            left: -1px;
            right: -1px;
            bottom: -1px;
            border-radius: 5px;
            padding: 1px;
            background: linear-gradient(45deg, transparent, var(--color-primary-muted), transparent);
            -webkit-mask: 
              linear-gradient(#fff 0 0) content-box, 
              linear-gradient(#fff 0 0);
            -webkit-mask-composite: xor;
            mask-composite: exclude;
            pointer-events: none;
          }
          
          /* Define keyframe animations */
          @keyframes fadeIn {
            from {
              opacity: 0;
              transform: translateY(10px);
            }
            to {
              opacity: 1;
              transform: translateY(0);
            }
          }
          
          @keyframes shake {
            0%, 100% { transform: translateX(0); }
            20% { transform: translateX(-8px); }
            40% { transform: translateX(8px); }
            60% { transform: translateX(-8px); }
            80% { transform: translateX(8px); }
          }
          
          /* Animation classes */
          .message.fade-in {
            animation: fadeIn 0.4s ease-out forwards;
          }
          
          .message.vibrate {
            animation: shake 0.5s cubic-bezier(.36,.07,.19,.97) both;
          }
          
          .chat-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 16px;
            background-color: var(--color-surface-raised);
            border-bottom: 1px solid var(--color-border-strong);
            height: 60px;
          }
          
          .header-title {
            display: flex;
            align-items: center;
            gap: 8px;
          }
          
          .header-icon {
            color: var(--color-primary);
            font-size: 1.2em;
          }
          
          .header-title h3 {
            margin: 0;
            font-size: 0.9em;
            letter-spacing: 1px;
            color: var(--color-text);
          }
          
          .connection-status {
            display: flex;
            align-items: center;
            gap: 8px;
          }
          
          .status-indicator {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background-color: var(--color-error);
            position: relative;
          }
          
          .status-indicator.connected {
            background-color: var(--color-success);
          }
          
          /* Pulsing effect for connected status */
          .status-indicator.connected::after {
            content: '';
            position: absolute;
            top: -4px;
            left: -4px;
            right: -4px;
            bottom: -4px;
            border-radius: 50%;
            background-color: var(--color-success);
            opacity: 0.3;
            animation: pulse 2s infinite;
            z-index: 0;
          }
          
          @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.5; }
            70% { transform: scale(1.1); opacity: 0.2; }
            100% { transform: scale(0.95); opacity: 0.5; }
          }
          
          .status-text {
            font-size: 0.75em;
            font-weight: 600;
            color: var(--color-text-secondary);
            letter-spacing: 0.5px;
          }
          
          .messages-container {
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            border-bottom: 1px solid var(--color-border-strong);
            background-color: var(--color-background);
            position: relative;
          }
          
          /* Grid overlay effect */
          .messages-container::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-image: 
              linear-gradient(var(--grid-color) 1px, transparent 1px),
              linear-gradient(90deg, var(--grid-color) 1px, transparent 1px);
            background-size: var(--grid-size) var(--grid-size);
            pointer-events: none;
            opacity: 0.3;
            z-index: 0;
          }
          
          .messages-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 16px;
            background-color: var(--color-surface);
            border-bottom: 1px solid var(--color-border);
            font-size: 0.7em;
            color: var(--color-text-secondary);
            height: 32px;
          }
          
          .channel-info {
            display: flex;
            gap: 8px;
          }
          
          .channel-label {
            color: var(--color-text-tertiary);
          }
          
          .channel-value {
            color: var(--color-primary);
            font-weight: 600;
          }
          
          .timestamp {
            font-family: monospace;
            color: var(--color-text-tertiary);
          }
          
          .messages {
            flex-grow: 1;
            overflow-y: auto;
            padding: 16px;
            position: relative;
            z-index: 1;
            
            /* Custom Scrollbar */
            scrollbar-width: thin;
            scrollbar-color: var(--color-primary) var(--color-surface);
          }
          
          .messages::-webkit-scrollbar {
            width: 6px;
          }
          
          .messages::-webkit-scrollbar-track {
            background: transparent;
          }
          
          .messages::-webkit-scrollbar-thumb {
            background-color: var(--color-primary);
            border-radius: 3px;
          }
          
          .message {
            margin: 12px 0;
            padding: 12px 16px;
            border-radius: 4px;
            max-width: 82%;
            word-wrap: break-word;
            line-height: 1.4;
            position: relative;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
          }
          
          .message.sent {
            background-color: var(--color-primary-muted);
            color: var(--color-text);
            margin-left: auto;
            margin-right: 4px;
            border-left: 3px solid var(--color-primary);
          }
          
          .message.received {
            background-color: var(--color-surface-raised);
            color: var(--color-text);
            margin-right: auto;
            margin-left: 4px;
            border-left: 3px solid var(--color-accent);
          }
          
          /* Style for error messages */
          .message.error {
            background-color: #ffebee; /* Light red background */
            color: #b71c1c; /* Darker red text */
            border-left-color: #d32f2f; /* Red border */
          }
          
          .message-header {
            display: flex;
            justify-content: space-between;
            font-size: 0.7em;
            margin-bottom: 6px;
            color: var(--color-text-secondary);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
          }
          
          .message-content {
            word-wrap: break-word;
            font-size: 0.9em;
            line-height: 1.5;
          }
          
          .message-footer {
            display: flex;
            justify-content: space-between;
            margin-top: 6px;
            padding-top: 4px;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            font-size: 0.65em;
            color: var(--color-text-tertiary);
            font-family: monospace;
          }
          
          .message-id {
            opacity: 0.7;
          }
          
          .reply-to {
            color: var(--color-primary);
          }
          
          .input-container {
            display: flex;
            gap: 8px;
            padding: 12px 16px;
            background-color: var(--color-surface-raised);
            border-top: 1px solid var(--color-border-strong);
            height: 64px;
          }
          
          input[type="text"] {
            flex: 1;
            padding: 0 16px;
            border: 1px solid var(--color-border-strong);
            border-radius: 4px;
            font-size: 0.9em;
            background-color: var(--color-surface);
            color: var(--color-text);
            font-family: inherit;
            height: 40px;
          }
          
          input[type="text"]:focus {
            border-color: var(--color-primary);
            box-shadow: 0 0 0 1px var(--color-primary-muted);
            outline: none;
          }
          
          input[type="text"]::placeholder {
            color: var(--color-text-tertiary);
          }
          
          .input-container button {
            height: 40px;
            padding: 0 20px;
            background-color: var(--color-surface-raised);
            color: var(--color-text);
            border: 1px solid var(--color-border-strong);
            border-radius: 4px;
            font-size: 0.8em;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            cursor: pointer;
            transition: all 0.2s;
          }
          
          .input-container button:hover:not(:disabled) {
            background-color: var(--color-primary);
            border-color: var(--color-primary);
            color: white;
          }
          
          .input-container button:active:not(:disabled) {
            transform: translateY(1px);
          }
          
          .input-container button:disabled {
            background-color: var(--color-surface);
            color: var(--color-text-tertiary);
            border-color: var(--color-border);
            cursor: not-allowed;
          }
        `}
      </style>
    </div>
  );
} 