import React, { useEffect } from 'react';
import { Grid, Box, Card, CardContent, Typography } from '@mui/material';
import { useAgentStore } from '../store/agentStore';
import AgentCard from './AgentCard';
import QueueChart from './QueueChart';
import StatusDistribution from './StatusDistribution';
import MessageFlow from './MessageFlow';
import MessageHistory from './MessageHistory';
import AgentQueues from './AgentQueues';

function AgentDashboard() {
  const { agents, connect, messages } = useAgentStore();

  useEffect(() => {
    connect();
    return () => {
      // Cleanup on unmount if needed
    };
  }, [connect]);

  return (
    <Box 
      sx={{ 
        height: '100vh',
        width: '100vw',
        overflow: 'auto',
        bgcolor: 'background.default',
        pt: '64px', // Account for header height
      }}
    >
      <Box sx={{ p: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
        {/* Message Flow - Full width and large */}
        <Card sx={{ width: '100%', height: '500px' }}>
          <CardContent sx={{ 
            height: '100%',
            p: 2,
            '&:last-child': { pb: 2 }
          }}>
            <Typography variant="h6" gutterBottom>
              Message Flow
            </Typography>
            <Box sx={{ height: 'calc(100% - 32px)' }}>
              <MessageFlow />
            </Box>
          </CardContent>
        </Card>

        {/* Message History and Agent Queues Row */}
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Card sx={{ height: '300px' }}>
              <CardContent sx={{ 
                height: '100%', 
                p: 2,
                '&:last-child': { pb: 2 },
                display: 'flex',
                flexDirection: 'column'
              }}>
                <Typography variant="h6" gutterBottom>
                  Message History
                </Typography>
                <Box sx={{ flexGrow: 1, overflow: 'hidden' }}>
                  <MessageHistory messages={messages} />
                </Box>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={6}>
            <Card sx={{ height: '300px' }}>
              <CardContent sx={{ height: '100%', p: 2, '&:last-child': { pb: 2 } }}>
                <AgentQueues agents={agents} />
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Charts Row */}
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <QueueChart agents={Object.values(agents)} />
          </Grid>
          <Grid item xs={12} md={6}>
            <StatusDistribution agents={Object.values(agents)} />
          </Grid>
        </Grid>

        {/* Agent Cards Row */}
        <Grid container spacing={2}>
          {Object.values(agents).map((agent) => (
            <Grid item xs={12} sm={6} md={4} lg={3} key={agent.id}>
              <AgentCard agent={agent} />
            </Grid>
          ))}
        </Grid>
      </Box>
    </Box>
  );
}

export default AgentDashboard; 