import React, { useEffect } from 'react';
import { Box, Paper, List, ListItem, ListItemText, Typography } from '@mui/material';

function EmptyState({ type }) {
  return (
    <Box 
      sx={{ 
        height: '100%', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        flexDirection: 'column',
        gap: 2,
        color: 'text.secondary'
      }}
    >
      <Typography variant="body1">
        {type === 'messages' 
          ? 'No messages yet. Start typing to interact with agents.' 
          : 'Waiting for agents to connect...'}
      </Typography>
    </Box>
  );
}

function MessageHistory({ messages }) {
  const messagesEndRef = React.useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  if (!messages.length) {
    return <EmptyState type="messages" />;
  }

  return (
    <Paper 
      sx={{ 
        height: '100%',
        overflowY: 'auto',
        bgcolor: 'background.paper',
        p: 1,
        '&::-webkit-scrollbar': {
          width: '8px',
        },
        '&::-webkit-scrollbar-track': {
          background: '#1a2027',
        },
        '&::-webkit-scrollbar-thumb': {
          background: '#888',
          borderRadius: '4px',
        },
      }}
    >
      <List>
        {messages.map((msg, index) => (
          <ListItem 
            key={`${msg.timestamp}-${index}`}
            sx={{
              borderRadius: 1,
              mb: 1,
              bgcolor: msg.sender_id ? 'background.paper' : 'primary.dark',
            }}
          >
            <ListItemText
              primary={
                <Typography variant="subtitle2" color="text.secondary">
                  {msg.sender_id ? msg.sender_name || 'Error' : 'Human'} {'to'} {msg.recipient_name || 'Unknown recipient'} • {new Date(msg.timestamp).toLocaleTimeString()}
                </Typography>
              }
              secondary={
                <Typography variant="body1" color="text.primary" sx={{ mt: 0.5 }}>
                  {msg.content}
                </Typography>
              }
            />
          </ListItem>
        ))}
        <div ref={messagesEndRef} />
      </List>
    </Paper>
  );
}

export default MessageHistory; 