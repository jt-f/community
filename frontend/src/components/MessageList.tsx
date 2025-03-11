import React, { useEffect, useRef } from 'react';
import {
  Box,
  Paper,
  Typography,
  Chip,
  List,
  ListItem,
  Stack,
  Avatar,
  Divider,
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
  type: string;
}

export const MessageList: React.FC = () => {
  const { messages, agents } = useAgentStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Debug logging
  useEffect(() => {
    console.log('Current agents:', agents);
    console.log('Current messages:', messages);
  }, [agents, messages]);

  // Scroll to bottom when messages change
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
  };

  // Function to get agent name from ID
  const getAgentName = (agentId: string): string => {
    // Check if the agent exists in our store
    if (agents[agentId]) {
      return agents[agentId].name;
    }
    
    // If not found in agents, check if it's a user ID from localStorage
    const userId = localStorage.getItem('userId');
    if (userId === agentId) {
      return 'You';
    }
    
    // If it's a human agent (might have a different ID format)
    const humanAgent = Object.values(agents).find(agent => 
      agent.type.toLowerCase() === 'human'
    );
    
    if (humanAgent && humanAgent.id === agentId) {
      return 'You';
    }
    
    // Default fallback
    return `Agent (${agentId.substring(0, 8)}...)`;
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
        p: 2,
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
      }}
    >
      {messages.length === 0 ? (
        <Box sx={{ 
          display: 'flex', 
          justifyContent: 'center', 
          alignItems: 'center', 
          height: '100%' 
        }}>
          <Typography variant="body1" color="text.secondary">
            No messages yet. Start a conversation!
          </Typography>
        </Box>
      ) : (
        messages.map((message, index) => {
          const isOutgoing = message.sender_id === localStorage.getItem('userId') || 
                            message.type === 'outgoing' ||
                            Object.values(agents).find(a => a.type === 'human')?.id === message.sender_id;
          
          const senderName = getAgentName(message.sender_id);
          
          return (
            <Paper 
              key={index} 
              elevation={1}
              sx={{ 
                p: 2, 
                maxWidth: '80%', 
                alignSelf: isOutgoing ? 'flex-end' : 'flex-start',
                backgroundColor: isOutgoing ? 'primary.light' : 'background.paper',
                color: isOutgoing ? 'primary.contrastText' : 'text.primary',
                borderRadius: 2
              }}
            >
              <Typography variant="subtitle2" fontWeight="bold" gutterBottom>
                {senderName}
              </Typography>
              
              <Typography variant="body1">
                {typeof message.content === 'string' 
                  ? message.content 
                  : message.content.text || JSON.stringify(message.content)}
              </Typography>
              
              <Typography variant="caption" color={isOutgoing ? 'primary.contrastText' : 'text.secondary'} sx={{ opacity: 0.7, display: 'block', textAlign: 'right', mt: 1 }}>
                {new Date(message.timestamp).toLocaleTimeString()}
              </Typography>
            </Paper>
          );
        })
      )}
      <div ref={messagesEndRef} />
    </Box>
  );
}; 