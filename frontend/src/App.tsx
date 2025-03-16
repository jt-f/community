import React, { useEffect } from 'react';
import { CssBaseline, ThemeProvider, Container, Box, Paper, Typography, GlobalStyles } from '@mui/material';
import { AgentDashboard } from './components/AgentDashboard';
import { MessageInput } from './components/MessageInput';
import { MessageList } from './components/MessageList';
import { useAgentStore } from './store/agentStore';
import { matrixTheme } from './theme/matrixTheme';

// Add global styles for Matrix-like effects
const globalStyles = (
  <GlobalStyles
    styles={{
      '@import': 'url("https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap")',
      '@keyframes matrixBg': {
        '0%': { backgroundPosition: '0% 0%' },
        '100%': { backgroundPosition: '100% 100%' }
      },
      'body': {
        margin: 0,
        fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
        overflow: 'hidden',
        position: 'relative',
        '&::before': {
          content: '""',
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          background: 'linear-gradient(rgba(0, 0, 0, 0.92), rgba(0, 0, 0, 0.96))',
          zIndex: -2,
        },
        '&::after': {
          content: '""',
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          backgroundImage: 'url("data:image/svg+xml,%3Csvg width=\'100%25\' height=\'100%25\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cdefs%3E%3Cpattern id=\'matrix\' width=\'20\' height=\'20\' patternUnits=\'userSpaceOnUse\'%3E%3Ctext x=\'0\' y=\'15\' font-size=\'10\' fill=\'%2300FF41\' opacity=\'0.2\'%3E1%3C/text%3E%3Ctext x=\'10\' y=\'10\' font-size=\'10\' fill=\'%2300FF41\' opacity=\'0.2\'%3E0%3C/text%3E%3C/pattern%3E%3C/defs%3E%3Crect width=\'100%25\' height=\'100%25\' fill=\'url(%23matrix)\'/%3E%3C/svg%3E")',
          opacity: 0.05,
          zIndex: -1,
          animation: 'matrixBg 60s linear infinite alternate',
        }
      },
      '#root': {
        height: '100vh',
        width: '100vw',
        overflow: 'auto',
      }
    }}
  />
);

function App() {
  const { connect, isConnected, agents } = useAgentStore();
  
  // Connect to WebSocket when the app loads
  useEffect(() => {
    connect();
    console.log('Connecting to WebSocket...');
    
    // Log connection status and agents for debugging
    return () => {
      console.log('WebSocket status:', isConnected);
    };
  }, [connect]);
  
  // Log when agents change
  useEffect(() => {
    console.log('Agents updated:', agents);
  }, [agents]);

  return (
    <ThemeProvider theme={matrixTheme}>
      <CssBaseline />
      {globalStyles}
      <Container 
        maxWidth="xl" 
        sx={{ 
          py: 3, 
          display: 'flex', 
          flexDirection: 'column', 
          height: '100vh',
          position: 'relative',
        }}
      >
        {/* Header */}
        <Box 
          sx={{ 
            mb: 3, 
            display: 'flex', 
            justifyContent: 'center',
            position: 'relative',
          }}
        >
          <Typography 
            variant="h3" 
            component="h1" 
            align="center"
            sx={{ 
              color: '#00FF41', 
              textShadow: '0 0 10px #00FF41, 0 0 20px #00FF41',
              fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              mb: 1,
              position: 'relative',
              '&::before': {
                content: '""',
                position: 'absolute',
                bottom: -8,
                left: '10%',
                width: '80%',
                height: '1px',
                background: 'linear-gradient(90deg, transparent, #00FF41, transparent)',
              }
            }}
          >
            Neural Network Command Center
          </Typography>
        </Box>
        
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
            border: '1px solid #003B00',
            borderRadius: '4px',
            minHeight: '50vh',
            backgroundColor: 'rgba(10, 10, 10, 0.8)',
            backdropFilter: 'blur(5px)',
            boxShadow: '0 0 15px rgba(0, 255, 65, 0.2), inset 0 0 10px rgba(0, 255, 65, 0.1)',
            position: 'relative',
            '&::before': {
              content: '""',
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '2px',
              background: 'linear-gradient(90deg, transparent, #00FF41, transparent)',
            }
          }}
        >
          <Box 
            sx={{ 
              flex: 1, 
              overflow: 'hidden', 
              display: 'flex', 
              flexDirection: 'column',
              position: 'relative',
            }}
          >
            <MessageList />
          </Box>
          <MessageInput />
        </Paper>
        
        {/* Footer */}
        <Box 
          sx={{ 
            mt: 2, 
            textAlign: 'center',
            opacity: 0.7,
          }}
        >
          <Typography 
            variant="caption" 
            sx={{ 
              color: '#00FF41',
              textShadow: '0 0 5px #00FF41',
              fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
              letterSpacing: '0.05em',
            }}
          >
            SYSTEM v1.0.1 // SECURE CONNECTION ESTABLISHED // {new Date().toISOString().split('T')[0]}
          </Typography>
        </Box>
      </Container>
    </ThemeProvider>
  );
}

export default App; 