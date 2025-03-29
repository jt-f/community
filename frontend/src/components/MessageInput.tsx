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
  keyframes,
  alpha,
  Tooltip,
  Chip,
} from '@mui/material';
import { 
  Send as SendIcon, 
  Terminal as TerminalIcon,
  Reply as ReplyIcon,
  Close as CloseIcon 
} from '@mui/icons-material';
import { useAgentStore } from '../store/agentStore';
import { useMessageStore } from '../store/messageStore';
import { generateShortId } from '../utils/idGenerator';

// Define keyframes for animations
const pulse = keyframes`
  0%, 100% { opacity: 0.8; }
  50% { opacity: 1; }
`;

const blink = keyframes`
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
`;

const scanline = keyframes`
  0% { transform: translateY(-100%); }
  100% { transform: translateY(100%); }
`;

export const MessageInput: React.FC = () => {
  const { 
    agents, 
    sendMessage, 
    isConnected, 
    connect, 
    socket
  } = useAgentStore();
  const { addMessage } = useMessageStore();
  const [message, setMessage] = useState('');
  const [selectedAgent, setSelectedAgent] = useState('all');
  const [isLoading, setIsLoading] = useState(true);
  const [humanAgentId, setHumanAgentId] = useState<string>('');
  const [isFocused, setIsFocused] = useState(false);

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
      const humanAgent = Object.values(agents).find((agent: any) => 
        agent.type.toLowerCase() === 'human'
      );
      
      if (humanAgent) {
        setHumanAgentId(humanAgent.id);
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
    
    // Use the human agent's ID from the agents list
    const userId = humanAgentId;
    
    // Generate a message ID early to use consistently
    const messageId = generateShortId();
    
    // Create the message object
    const messageObject = {
      message_id: messageId,
      sender_id: userId,
      receiver_id: selectedAgent === 'all' ? 'all' : selectedAgent,
      content: { text: message },
      message_type: 'text',
      timestamp: new Date().toISOString()
    };
    
    // Add the message to the UI first
    addMessage(messageObject);
    
    if (selectedAgent === 'all') {
      // Send to all non-human agents
      const nonHumanAgents = Object.values(agents).filter((agent: any) => 
        agent.type.toLowerCase() !== 'human'
      );
      
      if (nonHumanAgents.length > 0) {
        // Send to each agent using the stored broadcast message as the in_reply_to reference
        nonHumanAgents.forEach((agent) => {
          // Set addToUI to false since we already added the message to the messageStore
          sendMessage(message, agent.id, false, messageId);
        });
      } else {
        console.error('No non-human agents available');
      }
    } else {
      // Send to the selected agent through agentStore but don't add to UI again
      sendMessage(message, selectedAgent, false, messageId);
    }
    
    // Reset message state
    setMessage('');
  };

  // Create dynamic styles for the text field based on focus state
  const getTextFieldAfterStyles = () => {
    if (isFocused) {
      return {
        content: '""',
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        background: 'linear-gradient(180deg, transparent 0%, rgba(0, 255, 65, 0.05) 50%, transparent 100%)',
        animation: `${scanline} 2s linear infinite`,
      };
    }
    return {};
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
          borderTop: '1px solid #003B00',
          backgroundColor: 'rgba(10, 10, 10, 0.8)',
          position: 'relative',
          overflow: 'hidden',
          '&::before': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            background: 'repeating-linear-gradient(0deg, rgba(0, 255, 65, 0.03) 0px, rgba(0, 255, 65, 0.03) 1px, transparent 1px, transparent 2px)',
            pointerEvents: 'none',
            opacity: 0.5,
            zIndex: 1,
          }
        }}
      >
        <CircularProgress 
          size={20} 
          sx={{ 
            color: '#00FF41',
            animation: `${pulse} 1.5s infinite ease-in-out`,
          }} 
        />
        <Typography 
          variant="body2" 
          sx={{ 
            color: '#00FF41',
            fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
            letterSpacing: '0.05em',
            textShadow: '0 0 5px rgba(0, 255, 65, 0.5)',
            animation: `${blink} 2s infinite`,
          }}
        >
          {!isConnected ? 'ESTABLISHING NEURAL LINK...' : 'INITIALIZING AGENT PROTOCOLS...'}
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column' }}>
      {/* Input form */}
      <Paper 
        component="form" 
        onSubmit={handleSubmit} 
        sx={{ 
          p: 1.5, 
          display: 'flex', 
          alignItems: 'center',
          backgroundColor: 'rgba(10, 10, 10, 0.9)',
          backdropFilter: 'blur(5px)',
          borderTop: '1px solid #003B00',
          position: 'relative',
          overflow: 'hidden',
          '&::before': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            background: 'repeating-linear-gradient(0deg, rgba(0, 255, 65, 0.03) 0px, rgba(0, 255, 65, 0.03) 1px, transparent 1px, transparent 2px)',
            pointerEvents: 'none',
            opacity: 0.5,
            zIndex: 0,
          },
          '&::after': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '2px',
            background: 'linear-gradient(90deg, #FF8C00, #00FF41, #0047AB)',
            opacity: 0.7,
            zIndex: 1,
          }
        }}
      >
        <TerminalIcon 
          sx={{ 
            color: '#00FF41', 
            mr: 1.5, 
            opacity: 0.7,
            animation: `${pulse} 3s infinite ease-in-out`,
            position: 'relative',
            zIndex: 1,
            '&:hover': {
              color: '#FF8C00',
              animation: `${pulse} 1.5s infinite ease-in-out`,
            }
          }} 
        />
        
        <FormControl 
          variant="outlined" 
          size="small" 
          sx={{ 
            minWidth: 150, 
            mr: 1.5,
            position: 'relative',
            zIndex: 1,
            '& .MuiOutlinedInput-root': {
              color: '#00FF41',
              fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
              letterSpacing: '0.05em',
              borderColor: '#003B00',
              '&:hover .MuiOutlinedInput-notchedOutline': {
                borderColor: '#00FF41',
                boxShadow: '0 0 5px rgba(0, 255, 65, 0.5)',
              },
              '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
                borderColor: '#00FF41',
                borderWidth: '1px',
                boxShadow: '0 0 8px rgba(0, 255, 65, 0.7)',
              },
            },
            '& .MuiInputLabel-root': {
              color: 'rgba(0, 255, 65, 0.7)',
              fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
              letterSpacing: '0.05em',
              '&.Mui-focused': {
                color: '#00FF41',
              },
            },
            '& .MuiOutlinedInput-notchedOutline': {
              borderColor: '#003B00',
            },
            '& .MuiSvgIcon-root': {
              color: '#00FF41',
            },
          }}
        >
          <InputLabel id="agent-select-label">TARGET</InputLabel>
          <Select
            labelId="agent-select-label"
            id="agent-select"
            value={selectedAgent}
            onChange={(e) => setSelectedAgent(e.target.value)}
            label="TARGET"
            MenuProps={{
              PaperProps: {
                sx: {
                  backgroundColor: 'rgba(10, 10, 10, 0.95)',
                  backdropFilter: 'blur(10px)',
                  border: '1px solid #003B00',
                  boxShadow: '0 0 15px rgba(0, 255, 65, 0.3)',
                  '& .MuiMenuItem-root': {
                    color: '#00FF41',
                    fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                    letterSpacing: '0.05em',
                    '&:hover': {
                      backgroundColor: 'rgba(0, 255, 65, 0.1)',
                    },
                    '&.Mui-selected': {
                      backgroundColor: 'rgba(0, 255, 65, 0.2)',
                      '&:hover': {
                        backgroundColor: 'rgba(0, 255, 65, 0.3)',
                      },
                    },
                    '&:nth-of-type(3n+1)': {
                      borderLeft: '2px solid #FF8C00',
                    },
                    '&:nth-of-type(3n+2)': {
                      borderRight: '2px solid #0047AB',
                    },
                  },
                },
              },
            }}
          >
            <MenuItem value="all">ALL AGENTS</MenuItem>
            {Object.values(agents)
              .filter((agent: any) => agent.type?.toLowerCase() !== 'human')
              .map((agent: any) => (
                <MenuItem key={agent.id} value={agent.id}>
                  {agent.name || agent.id}
                </MenuItem>
              ))}
          </Select>
        </FormControl>
        
        <TextField
          fullWidth
          variant="outlined"
          placeholder="Enter command sequence..."
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          size="small"
          sx={{ 
            mr: 1.5,
            position: 'relative',
            zIndex: 1,
            '& .MuiOutlinedInput-root': {
              color: '#00FF41',
              fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
              letterSpacing: '0.05em',
              borderColor: '#003B00',
              transition: 'all 0.3s ease',
              '&:hover .MuiOutlinedInput-notchedOutline': {
                borderColor: '#00FF41',
                boxShadow: '0 0 5px rgba(0, 255, 65, 0.5)',
              },
              '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
                borderColor: '#00FF41',
                borderWidth: '1px',
                boxShadow: '0 0 8px rgba(0, 255, 65, 0.7)',
                borderImage: 'linear-gradient(45deg, #FF8C00, #00FF41, #0047AB) 1',
              },
              '&::after': getTextFieldAfterStyles(),
            },
            '& .MuiOutlinedInput-notchedOutline': {
              borderColor: '#003B00',
            },
            '& .MuiInputBase-input::placeholder': {
              color: 'rgba(0, 255, 65, 0.5)',
              opacity: 1,
            },
          }}
        />
        
        <IconButton 
          color="primary" 
          type="submit" 
          disabled={!message.trim()}
          sx={{
            color: '#00FF41',
            border: '1px solid #003B00',
            backgroundColor: 'rgba(0, 59, 0, 0.3)',
            transition: 'all 0.3s ease',
            position: 'relative',
            zIndex: 1,
            '&:hover': {
              backgroundColor: 'rgba(0, 255, 65, 0.1)',
              boxShadow: '0 0 10px rgba(0, 255, 65, 0.5)',
              transform: 'scale(1.05)',
              '&::before': {
                opacity: 1,
              }
            },
            '&:disabled': {
              color: 'rgba(0, 255, 65, 0.3)',
              borderColor: 'rgba(0, 59, 0, 0.3)',
            },
            '&::before': {
              content: '""',
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              borderRadius: '50%',
              padding: '2px',
              background: 'linear-gradient(45deg, #FF8C00, #00FF41, #0047AB)',
              mask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
              maskComposite: 'exclude',
              opacity: 0.7,
              transition: 'opacity 0.3s ease',
            }
          }}
        >
          <SendIcon />
        </IconButton>
      </Paper>
    </Box>
  );
};