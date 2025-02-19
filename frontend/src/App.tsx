import React from 'react';
import { CssBaseline, Container, Box, Paper } from '@mui/material';
import { MessageInput } from './components/MessageInput';
import { MessageList } from './components/MessageList';
import { AgentCard } from './components/AgentCard';
import { useWebSocket } from './hooks/useWebSocket';

const App: React.FC = () => {
  const { agents } = useWebSocket();

  return (
    <>
      <CssBaseline />
      <Container maxWidth="lg" sx={{ height: '100vh', display: 'flex', flexDirection: 'column', py: 2 }}>
        {/* Agent Cards */}
        <Box sx={{ mb: 2 }}>
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
              gap: 2,
            }}
          >
            {Object.values(agents).map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </Box>
        </Box>

        {/* Chat Container */}
        <Paper 
          elevation={3}
          sx={{ 
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            overflow: 'hidden',
            border: 1,
            borderColor: 'divider',
          }}
        >
          <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <MessageList />
          </Box>
          <MessageInput />
        </Paper>
      </Container>
    </>
  );
};

export default App; 