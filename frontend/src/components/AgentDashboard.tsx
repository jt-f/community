import React, { useState } from 'react';
import { Box, Button, Typography, Grid, Paper } from '@mui/material';
import { Add as AddIcon } from '@mui/icons-material';
import { AgentCard } from './AgentCard';
import { AgentCreationForm } from './AgentCreationForm';
import { useAgentStore } from '../store/agentStore';

export const AgentDashboard: React.FC = () => {
  const { agents } = useAgentStore();
  const [showCreationForm, setShowCreationForm] = useState(false);
  
  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4">Agent Dashboard</Typography>
        <Button 
          variant="contained" 
          startIcon={<AddIcon />}
          onClick={() => setShowCreationForm(!showCreationForm)}
        >
          {showCreationForm ? 'Hide Form' : 'Create New Agent'}
        </Button>
      </Box>
      
      {showCreationForm && <AgentCreationForm />}
      
      <Grid container spacing={3}>
        {Object.values(agents).map((agent) => (
          <Grid item xs={12} sm={6} md={4} key={agent.id}>
            <AgentCard agent={agent} />
          </Grid>
        ))}
        
        {Object.keys(agents).length === 0 && (
          <Grid item xs={12}>
            <Paper sx={{ p: 3, textAlign: 'center' }}>
              <Typography variant="body1" color="text.secondary">
                No agents available. Create a new agent to get started.
              </Typography>
            </Paper>
          </Grid>
        )}
      </Grid>
    </Box>
  );
}; 