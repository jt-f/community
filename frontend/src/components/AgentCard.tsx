import React from 'react';
import {
  Card,
  CardContent,
  Typography,
  Chip,
  Box,
  LinearProgress,
  Tooltip,
  IconButton,
  CardActions,
  Divider
} from '@mui/material';
import {
  Memory as MemoryIcon,
  Queue as QueueIcon,
  Update as UpdateIcon,
  Message as MessageIcon,
  Delete as DeleteIcon,
  Refresh as RefreshIcon
} from '@mui/icons-material';
import { useAgentStore } from '../store/agentStore';

// Update the interface to match what we have in the store
interface Agent {
  id: string;
  name: string;
  type: string;
  status: 'active' | 'busy' | 'offline';
  capabilities: string[];
  model?: string;
  provider?: string;
}

interface AgentCardProps {
  agent: Agent;
}

export const AgentCard: React.FC<AgentCardProps> = ({ agent }) => {
  const { sendMessage } = useAgentStore();
  
  const handleMessageClick = () => {
    // Implement message sending logic
    console.log(`Send message to ${agent.name}`);
  };
  
  const handleDeleteClick = () => {
    // Implement agent deletion logic
    console.log(`Delete agent ${agent.name}`);
  };
  
  const handleRefreshClick = () => {
    // Implement agent refresh logic
    console.log(`Refresh agent ${agent.name}`);
  };
  
  return (
    <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <CardContent sx={{ flexGrow: 1 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
          <Box>
            <Typography variant="h6" component="h2">
              {agent.name}
            </Typography>
            {(agent.model || agent.provider) && (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                {agent.model && `${agent.model}`}{agent.model && agent.provider && ' • '}{agent.provider && `${agent.provider}`}
              </Typography>
            )}
          </Box>
          <Chip 
            label={agent.status} 
            color={
              agent.status === 'active' ? 'success' : 
              agent.status === 'busy' ? 'warning' : 'error'
            }
            size="small"
          />
        </Box>
        
        <Box sx={{ mt: 2 }}>
          <Typography variant="caption" color="text.secondary">
            Capabilities:
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
            {agent.capabilities.map((cap, index) => (
              <Chip
                key={index}
                label={cap}
                size="small"
                variant="outlined"
                sx={{ fontSize: '0.7rem' }}
              />
            ))}
          </Box>
        </Box>

        <Typography color="text.secondary" gutterBottom>
          Type: {agent.type}
        </Typography>
      </CardContent>
      
      <CardActions sx={{ justifyContent: 'flex-end' }}>
        <IconButton size="small" onClick={handleMessageClick} title="Send Message">
          <MessageIcon />
        </IconButton>
        <IconButton size="small" onClick={handleRefreshClick} title="Refresh Agent">
          <RefreshIcon />
        </IconButton>
        <IconButton size="small" onClick={handleDeleteClick} title="Delete Agent">
          <DeleteIcon />
        </IconButton>
      </CardActions>
    </Card>
  );
}; 