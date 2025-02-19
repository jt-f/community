import React, { useState, useEffect } from 'react';
import {
  Box,
  TextField,
  Button,
  Typography,
  CircularProgress,
  Divider,
} from '@mui/material';
import { Send as SendIcon } from '@mui/icons-material';
import { useAgentStore } from '../store/agentStore';

export const MessageInput: React.FC = () => {
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const { isConnected, socket, connect } = useAgentStore();

  // Ensure connection is attempted when component mounts
  useEffect(() => {
    if (!isConnected) {
      connect();
    }
  }, [isConnected, connect]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim() || !isConnected) return;

    setSending(true);
    try {
      useAgentStore.getState().sendMessage({
        sender_id: 'human',
        content: {
          text: message.trim(),
          type: 'user_message'
        },
        message_type: 'text'
      });
      setMessage('');
    } catch (error) {
      console.error('Error sending message:', error);
    } finally {
      setSending(false);
    }
  };

  const getConnectionStatus = () => {
    if (!socket) return 'Not connected to server';
    switch (socket.readyState) {
      case WebSocket.CONNECTING:
        return 'Connecting to server...';
      case WebSocket.OPEN:
        return 'Connected';
      case WebSocket.CLOSING:
        return 'Connection closing...';
      case WebSocket.CLOSED:
        return 'Connection closed';
      default:
        return 'Not connected to server';
    }
  };

  const getStatusColor = () => {
    if (!socket) return 'error';
    switch (socket.readyState) {
      case WebSocket.OPEN:
        return 'success';
      case WebSocket.CONNECTING:
        return 'warning';
      default:
        return 'error';
    }
  };

  return (
    <>
      <Divider />
      <Box sx={{ p: 2, backgroundColor: 'background.paper' }}>
        <form onSubmit={handleSubmit}>
          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
            <Box sx={{ flexGrow: 1 }}>
              <TextField
                fullWidth
                variant="outlined"
                placeholder="Type your message..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                disabled={!isConnected || sending}
                InputProps={{
                  sx: { pr: 1 },
                  endAdornment: sending && (
                    <CircularProgress size={20} sx={{ mr: 1 }} />
                  ),
                }}
              />
              <Typography 
                variant="caption" 
                color={getStatusColor()}
                sx={{ mt: 0.5, display: 'block' }}
              >
                {getConnectionStatus()}
              </Typography>
            </Box>
            <Button
              variant="contained"
              color="primary"
              endIcon={<SendIcon />}
              type="submit"
              disabled={!isConnected || !message.trim() || sending}
              sx={{ height: 56 }}
            >
              Send
            </Button>
          </Box>
        </form>
      </Box>
    </>
  );
}; 