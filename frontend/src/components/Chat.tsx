import { useState, useEffect, useRef } from 'react';

interface Message {
  text: string;
  isEcho: boolean;
}

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8765/ws');

    ws.onopen = () => {
      setIsConnected(true);
      console.log('Connected to WebSocket server');
    };

    ws.onmessage = (event) => {
      setMessages(prev => [...prev, { text: event.data, isEcho: true }]);
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
      wsRef.current.send(inputMessage);
      setMessages(prev => [...prev, { text: inputMessage, isEcho: false }]);
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
        {messages.map((message, index) => (
          <div
            key={index}
            className={`message ${message.isEcho ? 'echo' : 'sent'}`}
          >
            {message.text}
          </div>
        ))}
      </div>
      <div className="input-container">
        <input
          type="text"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          onKeyPress={handleKeyPress}
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

        .message.echo {
          background-color: #e9ecef;
          color: #212529;
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