import React, { useEffect, useState } from 'react';
import ReactFlow, { 
  Background, 
  Controls,
  useNodesState,
  useEdgesState,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { io } from 'socket.io-client';

// Initialize socket connection
const socket = io('http://172.19.36.55:5000', {
  transports: ['websocket', 'polling'],
  reconnectionAttempts: Infinity,
  reconnectionDelay: 1000,
  reconnectionDelayMax: 5000,
  timeout: 20000,
  autoConnect: true
});

// Initial nodes
const initialNodes = [
  {
    id: 'user',
    data: { label: 'User' },
    position: { x: 250, y: 100 },
    style: { background: '#4CAF50', color: 'white' }
  },
  {
    id: 'system',
    data: { label: 'System' },
    position: { x: 250, y: 300 },
    style: { background: '#2196F3', color: 'white' }
  }
];

function App() {

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [messages, setMessages] = useState([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    // Socket event listeners
    socket.on('connect', () => {
      console.log('Connected to server');
      setConnected(true);
    });

    socket.on('disconnect', () => {
      console.log('Disconnected from server');
      setConnected(false);
    });

    socket.on('connect_error', (error) => {
      console.error('Connection error:', error);
    });

    socket.on('message', (message) => {
      console.log('Received message:', message);
      setMessages(prev => [...prev, message]);
      
      // Add new edge for the message
      const newEdge = {
        id: `e${Date.now()}`,
        source: message.from === 'user' ? 'user' : 'system',
        target: message.from === 'user' ? 'system' : 'user',
        label: message.text,
        animated: true,
        style: { stroke: '#888' }
      };

      setEdges(prev => [...prev, newEdge]);
    });

    return () => {
      socket.off('connect');
      socket.off('disconnect');
      socket.off('connect_error');
      socket.off('message');
    };
  }, [setEdges]);

  return (
    <div style={{ width: '100vw', height: '100vh' }}>
      {connected ? (
        <div style={{ position: 'absolute', top: 10, right: 10, color: '#4CAF50' }}>
          Connected
        </div>
      ) : (
        <div style={{ position: 'absolute', top: 10, right: 10, color: '#f44336' }}>
          Disconnected
        </div>
      )}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}

export default App; 