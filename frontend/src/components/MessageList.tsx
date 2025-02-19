import React, { useEffect, useRef } from 'react';
import {
  Box,
  Paper,
  Typography,
  Chip,
  List,
  ListItem,
  Stack,
} from '@mui/material';
import { useAgentStore } from '../store/agentStore';

interface Message {
  id: string;
  timestamp: string;
  sender_id: string;
  receiver_id?: string;
  content: {
    text?: string;
    status?: string;
    insights?: string[];
    [key: string]: any;
  };
  message_type: string;
}

export const MessageList: React.FC = () => {
  const { messages, agents } = useAgentStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Debug logging
  useEffect(() => {
    console.log('Current agents:', agents);
    console.log('Current messages:', messages);
  }, [agents, messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
  };

  const getAgentName = (id: string) => {
    console.log('Getting agent name for id:', id, 'Available agents:', agents);

    if (id === 'human') {
      return 'Human User';
    } else if (id === 'all') {
      return 'All agents';
    }
    const agent = agents[id];
    if (agent) {
      return `${agent.name} (${id})`;
    }
    return `Unknown Agent (${id})`;
  };

  const getMessageColor = (senderId: string) => {
    if (senderId === 'human') {
      return '#f5f5f5';  // Light grey
    }
    const agent = agents[senderId];
    if (!agent) return '#ffffff';  // White for unknown

    switch (agent.name.toLowerCase()) {
      case 'system':
        return '#e3f2fd';  // Light blue
      case 'analyst':
        return '#e8f5e9';  // Light green
      default:
        return '#ffffff';  // White
    }
  };

  const renderMessageContent = (content: Message['content']) => {
    if (typeof content === 'string') {
      return content;
    }

    if (content.text) {
      return content.text;
    }

    if (content.status) {
      return `Status: ${content.status}`;
    }

    return JSON.stringify(content);
  };

  const renderSecondaryContent = (content: Message['content']) => {
    if (!content) return null;

    return (
      <Box component="div" sx={{ mt: 1 }}>
        {content.insights && (
          <Box component="div" sx={{ mt: 1 }}>
            {content.insights.map((insight: string, index: number) => (
              <Box
                key={index}
                component="div"
                sx={{ 
                  ml: 2,
                  color: 'text.secondary',
                  fontSize: '0.875rem',
                }}
              >
                • {insight}
              </Box>
            ))}
          </Box>
        )}
        {content.status && (
          <Box
            component="div"
            sx={{ 
              mt: 1,
              color: 'text.secondary',
              fontSize: '0.875rem',
            }}
          >
            Status: {content.status}
          </Box>
        )}
      </Box>
    );
  };

  return (
    <Box
      sx={{
        flex: 1,
        overflow: 'auto',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <List sx={{ flex: 1, p: 2 }}>
        {messages.map((message: Message) => (
          <ListItem key={message.id} sx={{ mb: 1 }}>
            <Paper
              elevation={1}
              sx={{
                p: 2,
                width: '100%',
                backgroundColor: getMessageColor(message.sender_id),
                borderRadius: 2,
              }}
            >
              <Stack spacing={1}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                  <Chip
                    label={getAgentName(message.sender_id)}
                    size="small"
                    color="primary"
                    variant="outlined"
                  />
                  →
                  <Chip
                    label={message.receiver_id ? getAgentName(message.receiver_id) : 'all'}
                    size="small"
                    color="primary"
                    variant="outlined"
                  />
                  <Box
                    component="span"
                    sx={{ 
                      ml: 'auto',
                      color: 'text.secondary',
                      fontSize: '0.75rem',
                    }}
                  >
                    {formatTimestamp(message.timestamp)}
                  </Box>
                </Box>
                <Box>
                  <Box component="div" sx={{ fontSize: '1rem' }}>
                    {renderMessageContent(message.content)}
                  </Box>
                  {renderSecondaryContent(message.content)}
                </Box>
              </Stack>
            </Paper>
          </ListItem>
        ))}
        <div ref={messagesEndRef} />
      </List>
    </Box>
  );
}; 