import React, { useState, useEffect } from 'react';
import {
  Box,
  TextField,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Typography,
  CircularProgress,
  Divider,
  IconButton,
  Paper,
} from '@mui/material';
import { Send as SendIcon } from '@mui/icons-material';
import { useAgentStore } from '../store/agentStore';

export const MessageInput: React.FC = () => {
  const { 
    agents, 
    sendMessage, 
    isConnected, 
    connect, 
    addMessage,
    socket
  } = useAgentStore();
  const [message, setMessage] = useState('');
  const [selectedAgent, setSelectedAgent] = useState('all');
  const [isLoading, setIsLoading] = useState(true);
  const [humanAgentId, setHumanAgentId] = useState<string>('');

  // Ensure connection is established
  useEffect(() => {
    if (!isConnected) {
      connect();
    }
  }, [isConnected, connect]);

  // Update loading state based on agents and find human agent ID
  useEffect(() => {
    if (Object.keys(agents).length > 0) {
      setIsLoading(false);
      
      // Find the human agent by type
      const humanAgent = Object.values(agents).find(agent => 
        agent.type.toLowerCase() === 'human'
      );
      
      if (humanAgent) {
        setHumanAgentId(humanAgent.id);
        console.log('Found human agent ID:', humanAgent.id);
      } else {
        console.warn('Human agent not found, using default ID');
        setHumanAgentId('human');
      }
      
      // Reset selected agent if it's the human agent
      if (selectedAgent === humanAgentId) {
        setSelectedAgent('all');
      }
    }
  }, [agents, humanAgentId, selectedAgent]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim()) return;
    
    if (selectedAgent === 'all') {
      // Send to all non-human agents
      const nonHumanAgents = Object.values(agents).filter(agent => 
        agent.type.toLowerCase() !== 'human'
      );
      
      if (nonHumanAgents.length > 0) {
        // Add the message to the UI only once with the first agent
        sendMessage(message, nonHumanAgents[0].id, true);
        
        // Send to the rest of the agents without adding to UI
        for (let i = 1; i < nonHumanAgents.length; i++) {
          sendMessage(message, nonHumanAgents[i].id, false);
        }
      } else {
        console.error('No non-human agents available');
      }
    } else {
      // Send to the selected agent
      sendMessage(message, selectedAgent, true);
    }
    
    setMessage('');
  };

  if (!isConnected || isLoading) {
    return (
      <Box
        sx={{
          p: 2,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 2,
          borderTop: 1,
          borderColor: 'divider',
          backgroundColor: 'background.paper'
        }}
      >
        <CircularProgress size={20} />
        <Typography variant="body2" color="text.secondary">
          {!isConnected ? 'Connecting to server...' : 'Loading agents...'}
        </Typography>
      </Box>
    );
  }

  return (
    <Paper component="form" onSubmit={handleSubmit} sx={{ p: 1, display: 'flex', alignItems: 'center' }}>
      <FormControl variant="outlined" size="small" sx={{ minWidth: 120, mr: 1 }}>
        <InputLabel id="agent-select-label">Send to</InputLabel>
        <Select
          labelId="agent-select-label"
          value={selectedAgent}
          onChange={(e) => setSelectedAgent(e.target.value)}
          label="Send to"
        >
          <MenuItem value="all">All Agents</MenuItem>
          {Object.values(agents)
            .filter(agent => agent.type.toLowerCase() !== 'human') // Filter out human agents
            .map(agent => (
              <MenuItem key={agent.id} value={agent.id}>
                {agent.name}
              </MenuItem>
            ))}
        </Select>
      </FormControl>
      
      <TextField
        fullWidth
        variant="outlined"
        placeholder="Type a message..."
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        size="small"
        sx={{ mr: 1 }}
      />
      
      <IconButton color="primary" type="submit" disabled={!message.trim()}>
        <SendIcon />
      </IconButton>
    </Paper>
  );
};