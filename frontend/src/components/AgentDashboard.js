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
      <Box sx={{ p: 2, height: 'calc(100% - 16px)' }}>
        <Grid container spacing={2} sx={{ height: '100%' }}>
          {/* Top Row - 40% height */}
          <Grid item xs={12} sx={{ height: '40%' }}>
            <Grid container spacing={2} sx={{ height: '100%' }}>
              {/* Message History - 25% width */}
              <Grid item xs={3} sx={{ height: '100%' }}>
                <Card sx={{ height: '100%' }}>
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

              {/* Message Flow - 50% width */}
              <Grid item xs={6} sx={{ height: '100%' }}>
                <Card sx={{ height: '100%' }}>
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
              </Grid>

              {/* Agent Queues - 25% width */}
              <Grid item xs={3} sx={{ height: '100%' }}>
                <AgentQueues agents={agents} />
              </Grid>
            </Grid>
          </Grid>

          {/* Middle Row - 20% height */}
          <Grid item xs={12} sx={{ height: '20%' }}>
            <Grid container spacing={2} sx={{ height: '100%' }}>
              <Grid item xs={6} sx={{ height: '100%' }}>
                <QueueChart agents={Object.values(agents)} />
              </Grid>
              <Grid item xs={6} sx={{ height: '100%' }}>
                <StatusDistribution agents={Object.values(agents)} />
              </Grid>
            </Grid>
          </Grid>

          {/* Bottom Row - 40% height */}
          <Grid item xs={12} sx={{ height: '40%' }}>
            <Grid container spacing={2} sx={{ height: '100%' }}>
              {Object.values(agents).map((agent) => (
                <Grid item xs={12} sm={6} md={4} lg={3} key={agent.id} sx={{ height: '100%' }}>
                  <AgentCard agent={agent} />
                </Grid>
              ))}
            </Grid>
          </Grid>
        </Grid>
      </Box>
    </Box>
  );
}

export default AgentDashboard; 