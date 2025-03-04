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
} from '@mui/material';
import { Send as SendIcon } from '@mui/icons-material';
import { useAgentStore } from '../store/agentStore';

export const MessageInput: React.FC = () => {
  const { agents, sendMessage, isConnected, connect } = useAgentStore();
  const [message, setMessage] = useState('');
  const [selectedAgent, setSelectedAgent] = useState<string>('all');
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
      
      // Find the human agent by name
      const humanAgent = Object.values(agents).find(agent => 
        agent.name.toLowerCase() === 'human' || 
        agent.name.toLowerCase().includes('human')
      );
      
      if (humanAgent) {
        setHumanAgentId(humanAgent.id);
        console.log('Found human agent ID:', humanAgent.id);
      } else {
        console.warn('Human agent not found, using default ID');
        setHumanAgentId('human');
      }
    }
  }, [agents]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (message.trim()) {
      sendMessage({
        sender_id: humanAgentId || 'human', // Use the found human agent ID or fallback to 'human'
        receiver_id: selectedAgent === 'all' ? undefined : selectedAgent,
        content: {
          text: message,
          timestamp: new Date().toISOString()
        },
        message_type: 'text'
      });
      setMessage('');
    }
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
    <Box
      component="form"
      onSubmit={handleSubmit}
      sx={{
        p: 2,
        display: 'flex',
        gap: 1,
        borderTop: 1,
        borderColor: 'divider',
        backgroundColor: 'background.paper'
      }}
    >
      <FormControl size="small" sx={{ minWidth: 200 }}>
        <InputLabel id="send-to-label">Send to</InputLabel>
        <Select
          labelId="send-to-label"
          value={selectedAgent}
          onChange={(e) => setSelectedAgent(e.target.value)}
          label="Send to"
        >
          <MenuItem value="all">All Agents</MenuItem>
          {Object.entries(agents).map(([id, agent]) => (
            <MenuItem key={id} value={id}>
              {agent.name} ({id})
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <TextField
        fullWidth
        size="small"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="Type your message..."
        variant="outlined"
        disabled={!isConnected}
      />

      <Button 
        type="submit" 
        variant="contained" 
        disabled={!message.trim() || !isConnected}
        endIcon={<SendIcon />}
      >
        Send
      </Button>
    </Box>
  );
};