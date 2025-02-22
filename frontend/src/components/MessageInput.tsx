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
  const { agents, sendMessage } = useAgentStore();
  const [message, setMessage] = useState('');
  const [selectedAgent, setSelectedAgent] = useState<string>('all');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (message.trim()) {
      sendMessage({
        sender_id: 'human',
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
      <FormControl size="small" sx={{ minWidth: 200 }} component={Box}>
        <InputLabel id="send-to-label">Send to</InputLabel>
        <Select
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
      />

      <Button type="submit" variant="contained" disabled={!message.trim()}>
        Send
      </Button>
    </Box>
  );
};