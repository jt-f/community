import React, { useState, useEffect, useRef, useContext } from 'react';
import { ChatMessage, MessageType, createMessage } from '../types/message';
import { WebSocketContext } from './ChatUI';

interface ChatProps {
  wsRef: React.RefObject<WebSocket | null>;
  isConnected: boolean;
  userId: string;
}

interface MessageWithAnimation extends ChatMessage {
  isNew?: boolean;
  animationPhase?: 'fadeIn' | 'vibrate' | null;
  status?: 'pending' | 'routed' | 'error' | 'routing_failed';
  routedTo?: string;
  _routing_status?: 'pending' | 'routed' | 'routing_failed';
}

const Chat = ({ wsRef, userId }: ChatProps): React.ReactElement => {
  const [messages, setMessages] = useState<MessageWithAnimation[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const sentMessageIds = useRef<Set<string>>(new Set());
  const [clientId, setClientId] = useState<string | null>(userId);
  const { lastMessage, sendMessage } = useContext(WebSocketContext);

  // Handle incoming messages from WebSocketContext
  useEffect(() => {
    if (!lastMessage) return;

    const messageId = lastMessage.message_id;
    const routingStatus = lastMessage._routing_status;
    const messageType = lastMessage.message_type;

    // --- Skip processing for Agent Status Updates --- 
    if (messageType === MessageType.AGENT_STATUS_UPDATE) {
      console.log('Received AGENT_STATUS_UPDATE, ignoring for chat display:', lastMessage);
      // TODO: Update agent status display if needed elsewhere
      return; // Don't process this as a chat message
    }
    // -----------------------------------------------

    // console.log('Chat component received message from context:', lastMessage, `Routing Status: ${routingStatus}`);

    // Handle registration response separately
    if (messageType === MessageType.REGISTER_FRONTEND_RESPONSE && lastMessage.status === 'success') {
        console.log('Registration confirmed in Chat:', lastMessage);
        setClientId(lastMessage.frontend_id);
        return;
    }

    // Find existing message by ID
    const existingMessageIndex = messages.findIndex(m => m.message_id === messageId);

    if (existingMessageIndex !== -1) {
        // --- Update Existing Message ---
        // console.log(`Updating existing message ID ${messageId} with status info: ${routingStatus}`);
        setMessages(prev =>
            prev.map((msg, index) => {
                if (index === existingMessageIndex) {
                    // Determine final status based on routing status or message type
                    let finalStatus: MessageWithAnimation['status'] = msg.status;
                    if (routingStatus === 'routed') finalStatus = 'routed';
                    else if (routingStatus === 'pending') finalStatus = 'pending';
                    else if (routingStatus === 'routing_failed') finalStatus = 'error';
                    else if (messageType === MessageType.ERROR && msg.status !== 'error') finalStatus = 'error';

                    return {
                        ...msg,
                        ...lastMessage,
                        message_id: msg.message_id,
                        status: finalStatus,
                        routedTo: finalStatus === 'routed' ? lastMessage.receiver_id : msg.routedTo,
                        animationPhase: msg.status !== finalStatus ? 'vibrate' : null,
                        isNew: false
                    };
                }
                return msg;
            })
        );
        // Clear vibrate animation after a short delay if it was triggered
        if (messages[existingMessageIndex]?.status !== (routingStatus || messages[existingMessageIndex]?.status)) {
            setTimeout(() => {
                setMessages(msgs =>
                    msgs.map((m, i) =>
                        i === existingMessageIndex ? { ...m, animationPhase: null } : m
                    )
                );
            }, 300);
        }

    } else {
        // --- Add New Message (only if not sent by self) ---
        if (lastMessage.sender_id === clientId) {
             if (!sentMessageIds.current.has(messageId)) {
                  console.warn(`Received message ID ${messageId} matching self clientId, but not found locally or in sentMessageIds. Adding.`);
             } else {
                  console.log(`Ignoring new message ID ${messageId} from self - already added by handleSendMessage or will be updated.`);
                  return;
             }
        }

        console.log(`Adding new message ID ${messageId} from sender ${lastMessage.sender_id}`);

        // Determine initial status for a newly received message
        let initialStatus: MessageWithAnimation['status'] = 'error';
        if (routingStatus === 'routed') initialStatus = 'routed';
        else if (routingStatus === 'pending') initialStatus = 'pending';
        else if (routingStatus === 'routing_failed') initialStatus = 'error';
        else if (messageType === MessageType.ERROR) initialStatus = 'error';
        else if (messageType === MessageType.TEXT || messageType === MessageType.REPLY || messageType === MessageType.SYSTEM) {
             initialStatus = 'routed';
        }

        const newMessage: MessageWithAnimation = {
            ...lastMessage,
            isNew: true,
            animationPhase: 'fadeIn',
            status: initialStatus,
            routedTo: initialStatus === 'routed' ? lastMessage.receiver_id : undefined
        };

        setMessages(prev => [...prev, newMessage]);
    }

  }, [lastMessage, clientId]);

  // Auto-scroll when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = () => {
    if (inputMessage.trim() && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      const message = createMessage(
        clientId || '',
        'server',
        inputMessage,
        MessageType.TEXT
      );
      
      const messageWithAnimation: MessageWithAnimation = {
        ...message,
        isNew: true,
        animationPhase: 'fadeIn',
        status: 'pending'
      };
      
      sentMessageIds.current.add(message.message_id);
      sendMessage(message);
      setMessages(prev => [...prev, messageWithAnimation]);
      setInputMessage('');
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSendMessage();
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

  // Function to get display text for status
  const getStatusText = (status: MessageWithAnimation['status'], routedTo?: string): string => {
      switch(status) {
          case 'pending': return 'AWAITING ROUTING';
          case 'routed': return `ROUTED TO: ${routedTo || '?'}`;
          case 'error': return 'ERROR';
          case 'routing_failed': return 'ROUTING FAILED';
          default: return '';
      }
  };

  return (
    <div className="chat-container">
      <div className="chat-header">
        <div className="header-title">
          <span className="header-icon">⚡</span>
          <h3>SECURE COMMUNICATIONS</h3>
        </div>
        <div className="connection-status">
          <div className={`status-indicator ${wsRef.current ? 'connected' : 'disconnected'}`}></div>
          <span className="status-text">{wsRef.current ? 'CONNECTED' : 'DISCONNECTED'}</span>
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
              key={message.message_id || `msg_${index}_${Date.now()}`}
              className={`message 
                ${message.sender_id === clientId ? 'sent' : 'received'} 
                ${message.animationPhase === 'fadeIn' ? 'fade-in' : ''}
                ${message.animationPhase === 'vibrate' ? 'vibrate' : ''}
                status-${message.status || 'unknown'}`}
              onAnimationEnd={() => {
                if (message.animationPhase === 'fadeIn') {
                  handleFadeInComplete(index);
                }
              }}
            >
              <div className="message-header">
                <div className="message-directions">
                  <span className="message-from">FROM: {message.sender_id === clientId ? 'You' : message.sender_id}</span>
                  <span className="message-to">TO: {message.status === 'routed' && message.routedTo ? message.routedTo : (message.receiver_id || '?')}</span>
                </div>
                <span className="timestamp">{message.send_timestamp}</span>
              </div>
              <div className="message-content">
                {message.text_payload}
              </div>
              <div className="message-footer">
                <span className="message-id">ID: {message.message_id ? message.message_id.substring(0, 8) : 'unknown'}</span>
                {(message.status === 'pending' || message.status === 'routed' || message.status === 'error' || message.status === 'routing_failed') && (
                  <span className={`routing-status ${message.status}`}>
                    {getStatusText(message.status, message.routedTo)}
                  </span>
                )}
                {message.status === 'routed' && (
                  <span className="routing-status routed">ROUTED TO: {message.routedTo}</span>
                )}
                {message.status === 'error' && (
                  <span className="routing-status error">ERROR</span>
                )}
                {message.message_type === MessageType.REPLY && message.in_reply_to_message_id && (
                  <span className="reply-to">↩ {message.in_reply_to_message_id.substring(0, 8)}</span>
                )}
              </div>
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
          disabled={!wsRef.current}
        />
        <button onClick={handleSendMessage} disabled={!wsRef.current}>
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
          
          /* Pending message style - amber/yellow highlight */
          .message.sent.pending {
            background-color: rgba(255, 193, 7, 0.1);
            border-left: 3px solid #FFC107; /* Amber color */
          }
          
          /* Routed message style - green highlight */
          .message.sent.routed {
            background-color: rgba(76, 175, 80, 0.1);
            border-left: 3px solid #4CAF50; /* Green color */
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
          
          /* Style for informational messages */
          .message.info {
            background-color: #f5f5f5; /* Light grey background */
            color: #424242; /* Darker grey text */
            border-left-color: #9e9e9e; /* Grey border */
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
          
          .message-directions {
            display: flex;
            flex-direction: column;
            gap: 2px;
          }
          
          .message-from, .message-to {
            display: flex;
            align-items: center;
          }
          
          .message-from {
            color: var(--color-primary);
          }
          
          .message-to {
            color: var(--color-accent);
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
          
          .routing-status {
            font-weight: bold;
            letter-spacing: 0.5px;
          }
          
          .routing-status.pending {
            color: #FFC107; /* Amber color */
          }
          
          .routing-status.routed {
            color: #4CAF50; /* Green color */
          }
          
          .routing-status.error {
            color: #b71c1c; /* Red color */
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
};

export default Chat; 