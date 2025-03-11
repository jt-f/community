import React, { useEffect } from 'react';
import { CssBaseline, ThemeProvider, createTheme, Container, Box, Paper } from '@mui/material';
import { AgentDashboard } from './components/AgentDashboard';
import { MessageInput } from './components/MessageInput';
import { MessageList } from './components/MessageList';
import { useAgentStore } from './store/agentStore';

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
  },
});

function App() {
  const { connect, isConnected, agents } = useAgentStore();
  
  // Connect to WebSocket when the app loads
  useEffect(() => {
    connect();
    console.log('Connecting to WebSocket...');
    
    // Log connection status and agents for debugging
    return () => {
      console.log('App unmounting, WebSocket status:', isConnected);
    };
  }, [connect]);
  
  // Log when agents change
  useEffect(() => {
    console.log('Agents updated:', agents);
  }, [agents]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Container maxWidth="xl" sx={{ py: 3, display: 'flex', flexDirection: 'column', height: '100vh' }}>
        {/* Agent Dashboard */}
        <Box sx={{ mb: 3 }}>
          <AgentDashboard />
        </Box>
        
        {/* Chat Interface */}
        <Paper 
          elevation={3}
          sx={{ 
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            border: 1,
            borderColor: 'divider',
            minHeight: '50vh',
          }}
        >
          <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <MessageList />
          </Box>
          <MessageInput />
        </Paper>
      </Container>
    </ThemeProvider>
  );
}

export default App; 