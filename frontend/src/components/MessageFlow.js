import React, { useEffect } from 'react';
import ReactFlow, { 
  Background, 
  Controls,
  useNodesState,
  useEdgesState,
  MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Box, Card, CardContent, Typography, CircularProgress } from '@mui/material';
import { useAgentStore } from '../store/agentStore';

// Custom node styles
const nodeStyle = {
  padding: 10,
  borderRadius: 5,
  border: '1px solid #777',
  background: '#1a2027',
  color: '#fff',
  width: 150,
};

const humanNodeStyle = {
  ...nodeStyle,
  background: '#2196f3',
};

function MessageFlow() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const { agents, messages, connected } = useAgentStore();
  const [isInitialized, setIsInitialized] = React.useState(false);

  // Initialize with Human node even if no agents are connected
  useEffect(() => {
    const initialNodes = [{
      id: 'human',
      data: { label: 'Human' },
      position: { x: 300, y: 200 },
      style: humanNodeStyle,
    }];
    setNodes(initialNodes);
    setIsInitialized(true);
  }, [setNodes]);

  // Update nodes when agents change
  useEffect(() => {
    if (!isInitialized) return;

    const agentNodes = Object.values(agents).map((agent) => ({
      id: agent.id,
      position: { x: 0, y: 0 },
      data: { label: agent.name },
      style: nodeStyle,
    }));

    const allNodes = [
      {
        id: 'human',
        data: { label: 'Human' },
        position: { x: 0, y: 0 },
        style: humanNodeStyle,
      },
      ...agentNodes,
    ];

    // Position nodes in a circle
    const radius = 200;
    const angleStep = (2 * Math.PI) / allNodes.length;
    allNodes.forEach((node, index) => {
      const angle = index * angleStep;
      node.position = {
        x: 300 + radius * Math.cos(angle),
        y: 200 + radius * Math.sin(angle),
      };
    });

    setNodes(allNodes);
  }, [agents, setNodes, isInitialized]);

  // Update edges when messages change
  useEffect(() => {
    if (!messages.length) {
      setEdges([]);
      return;
    }

    // Get set of valid agent IDs (including 'human')
    const validIds = new Set(['human', ...Object.keys(agents)]);

    // Create a map to track latest message between each pair
    const latestMessages = new Map();
    
    // Process messages in chronological order, but only for active agents
    messages.forEach((msg) => {
      const source = msg.sender_id || 'human';
      const target = msg.recipient_id || 'human';
      
      // Only create edges between valid nodes
      if (validIds.has(source) && validIds.has(target)) {
        const pairKey = `${source}-${target}`;
        
        // Update the latest message for this pair
        if (!latestMessages.has(pairKey) || 
            new Date(msg.timestamp) > new Date(latestMessages.get(pairKey).timestamp)) {
          latestMessages.set(pairKey, msg);
        }
      }
    });

    // Create edges from latest messages
    const newEdges = Array.from(latestMessages.entries())
      .map(([pairKey, msg]) => {
        const source = msg.sender_id || 'human';
        const target = msg.recipient_id || 'human';
        
        return {
          id: `${pairKey}-${msg.timestamp}`,
          source,
          target,
          type: 'smoothstep',
          animated: true,
          style: { stroke: '#90caf9' },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: '#90caf9',
          },
          label: msg.content.substring(0, 20) + (msg.content.length > 20 ? '...' : ''),
          labelStyle: { fill: '#fff', fontSize: 12 },
          labelBgStyle: { fill: '#1a2027', fillOpacity: 0.7 },
          data: { timestamp: msg.timestamp },
        };
      });

    setEdges(newEdges);
  }, [messages, agents, setEdges]);

  if (!connected) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ height: '100%' }}>
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
    </Box>
  );
}

export default MessageFlow; 