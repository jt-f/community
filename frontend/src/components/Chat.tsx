import { useState, useEffect, useRef } from 'react';
import { ChatMessage, MessageType, createMessage } from '../types/message';

export function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const userId = useRef(`user_${Math.random().toString(36).substring(2, 11)}`);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8765/ws');

    ws.onopen = () => {
      setIsConnected(true);
      console.log('Connected to WebSocket server');
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as ChatMessage;
        setMessages(prev => [...prev, message]);
      } catch (error) {
        console.error('Failed to parse message:', error);
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      console.log('Disconnected from WebSocket server');
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setIsConnected(false);
    };

    wsRef.current = ws;

    return () => {
      ws.close();
    };
  }, []);

  const sendMessage = () => {
    if (inputMessage.trim() && wsRef.current?.readyState === WebSocket.OPEN) {
      const message = createMessage(
        userId.current,
        'server',
        inputMessage,
        MessageType.TEXT
      );
      
      wsRef.current.send(JSON.stringify(message));
      setMessages(prev => [...prev, message]);
      setInputMessage('');
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      sendMessage();
    }
  };

  return (
    <div className="chat-container">
      <div className="connection-status">
        Status: {isConnected ? 'Connected' : 'Disconnected'}
      </div>
      <div className="messages">
        {messages.map((message) => (
          <div
            key={message.message_id}
            className={`message ${message.sender_id === userId.current ? 'sent' : 'received'}`}
          >
            <div className="message-header">
              <span className="sender">{message.sender_id}</span>
              <span className="timestamp">
                {new Date(message.send_timestamp).toLocaleTimeString()}
              </span>
            </div>
            <div className="message-content">
              {message.text_payload}
              {message.in_reply_to_message_id && (
                <div className="reply-indicator">
                  Replying to message: {message.in_reply_to_message_id}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
      <div className="input-container">
        <input
          type="text"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyUp={handleKeyPress}
          placeholder="Type a message..."
          disabled={!isConnected}
        />
        <button onClick={sendMessage} disabled={!isConnected}>
          Send
        </button>
      </div>
      <style>{`
        .chat-container {
          max-width: 600px;
          margin: 0 auto;
          padding: 20px;
          border: 1px solid #ccc;
          border-radius: 8px;
          background-color: #f9f9f9;
        }

        .connection-status {
          margin-bottom: 10px;
          padding: 5px;
          border-radius: 4px;
          background-color: ${isConnected ? '#e6ffe6' : '#ffe6e6'};
          text-align: center;
        }

        .messages {
          height: 400px;
          overflow-y: auto;
          margin-bottom: 20px;
          padding: 10px;
          border: 1px solid #ddd;
          border-radius: 4px;
          background-color: white;
        }

        .message {
          margin: 5px 0;
          padding: 8px 12px;
          border-radius: 4px;
          max-width: 80%;
        }

        .message.sent {
          background-color: #007bff;
          color: white;
          margin-left: auto;
        }

        .message.received {
          background-color: #e9ecef;
          color: #212529;
        }

        .message-header {
          display: flex;
          justify-content: space-between;
          font-size: 0.8em;
          margin-bottom: 4px;
        }

        .message-content {
          word-wrap: break-word;
        }

        .reply-indicator {
          font-size: 0.8em;
          margin-top: 4px;
          padding-top: 4px;
          border-top: 1px solid rgba(255, 255, 255, 0.2);
        }

        .input-container {
          display: flex;
          gap: 10px;
        }

        input {
          flex: 1;
          padding: 8px;
          border: 1px solid #ddd;
          border-radius: 4px;
          font-size: 16px;
        }

        button {
          padding: 8px 16px;
          background-color: #007bff;
          color: white;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-size: 16px;
        }

        button:disabled {
          background-color: #ccc;
          cursor: not-allowed;
        }
      `}</style>
    </div>
  );
} 