import React, { useEffect, useState } from 'react';
import { ThemeProvider, createTheme, CssBaseline } from '@mui/material';
import { Box, Tab, Tabs } from '@mui/material';
import ReactFlow, { 
  Background, 
  Controls,
  useNodesState,
  useEdgesState,
} from 'reactflow';
import 'reactflow/dist/style.css';
import AgentDashboard from './components/AgentDashboard';
import Header from './components/Header';

// WebSocket connection
const WS_URL = 'ws://172.19.36.55:8000/ws';

// Initial nodes
const initialNodes = [
  {
    id: 'human',
    data: { label: 'Human' },
    position: { x: 250, y: 100 },
    style: { background: '#4CAF50', color: 'white' }
  }
];

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#90caf9',
    },
    secondary: {
      main: '#f48fb1',
    },
    background: {
      default: '#0a1929',
      paper: '#1a2027',
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
    h1: {
      fontSize: '2.5rem',
      fontWeight: 500,
    },
    h2: {
      fontSize: '2rem',
      fontWeight: 500,
    },
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundImage: 'linear-gradient(rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.05))',
          backdropFilter: 'blur(20px)',
        },
      },
    },
  },
});

function TabPanel({ children, value, index }) {
  return (
    <Box
      role="tabpanel"
      hidden={value !== index}
      sx={{
        flexGrow: 1,
        display: value === index ? 'flex' : 'none',
        height: 'calc(100vh - 112px)', // Adjust for header and tabs
      }}
    >
      {value === index && children}
    </Box>
  );
}

function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [messages, setMessages] = useState([]);
  const [connected, setConnected] = useState(false);
  const [ws, setWs] = useState(null);
  const [tabValue, setTabValue] = useState(0);

  useEffect(() => {
    const connectWebSocket = () => {
      const websocket = new WebSocket(WS_URL);

      websocket.onopen = () => {
        console.log('Connected to server');
        setConnected(true);
      };

      websocket.onclose = () => {
        console.log('Disconnected from server');
        setConnected(false);
        // Try to reconnect in 2 seconds
        setTimeout(connectWebSocket, 2000);
      };

      websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      websocket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          console.log('Received message:', message);
          
          if (message.type === 'message') {
            setMessages(prev => [...prev, message.data]);
            
            // Add new edge for the message
            const newEdge = {
              id: `e${Date.now()}`,
              source: message.data.sender_id || 'human',
              target: message.data.recipient_id || 'human',
              label: message.data.content,
              animated: true,
              style: { stroke: '#888' }
            };

            // Add any new agent nodes that we haven't seen before
            setNodes(nodes => {
              const existingIds = new Set(nodes.map(n => n.id));
              const newNodes = [];
              
              // Add source node if it's new
              if (!existingIds.has(newEdge.source)) {
                newNodes.push({
                  id: newEdge.source,
                  data: { label: message.data.sender_name || newEdge.source },
                  position: { x: 250 + Math.random() * 100, y: 200 + Math.random() * 100 },
                  style: newEdge.source === 'human' ? 
                    { background: '#4CAF50', color: 'white' } : 
                    { background: '#2196F3', color: 'white' }
                });
              }
              
              // Add target node if it's new and different from source
              if (!existingIds.has(newEdge.target) && newEdge.target !== newEdge.source) {
                newNodes.push({
                  id: newEdge.target,
                  data: { label: message.data.recipient_name || newEdge.target },
                  position: { x: 250 + Math.random() * 100, y: 200 + Math.random() * 100 },
                  style: newEdge.target === 'human' ? 
                    { background: '#4CAF50', color: 'white' } : 
                    { background: '#2196F3', color: 'white' }
                });
              }
              
              return newNodes.length ? [...nodes, ...newNodes] : nodes;
            });

            setEdges(prev => [...prev, newEdge]);
          }
        } catch (error) {
          console.error('Error parsing message:', error);
          console.error('Raw message data:', event.data);
        }
      };

      setWs(websocket);

      // Cleanup on unmount
      return () => {
        websocket.close();
      };
    };

    connectWebSocket();
  }, [setEdges]);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          background: 'linear-gradient(45deg, #0a1929 30%, #1a2027 90%)',
        }}
      >
        <Header />
        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          sx={{
            borderBottom: 1,
            borderColor: 'divider',
            bgcolor: 'background.paper',
          }}
        >
          <Tab label="Flow View" />
          <Tab label="Dashboard" />
        </Tabs>

        <TabPanel value={tabValue} index={0}>
          <Box sx={{ width: '100%', height: '100%' }}>
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
        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          <AgentDashboard />
        </TabPanel>
      </Box>
    </ThemeProvider>
  );
}

export default App; 