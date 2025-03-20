import React, { useEffect, useRef, useState } from 'react';
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
  keyframes,
  alpha,
} from '@mui/material';
import { 
  Computer as ComputerIcon, 
  Person as PersonIcon,
  Code as CodeIcon,
  Memory as MemoryIcon
} from '@mui/icons-material';
import { useAgentStore } from '../store/agentStore';
import { getAgentName } from '../utils/agentUtils';

// Define keyframes for animations
const typing = keyframes`
  from { width: 0 }
  to { width: 100% }
`;

const blink = keyframes`
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
`;

const pulse = keyframes`
  0%, 100% { opacity: 0.8; }
  50% { opacity: 1; }
`;

const scanline = keyframes`
  0% { transform: translateY(-100%); }
  100% { transform: translateY(100%); }
`;

const glitch = keyframes`
  0% {
    clip-path: inset(40% 0 61% 0);
    transform: translate(-2px, 2px);
  }
  20% {
    clip-path: inset(92% 0 1% 0);
    transform: translate(1px, 3px);
  }
  40% {
    clip-path: inset(43% 0 1% 0);
    transform: translate(3px, 1px);
  }
  60% {
    clip-path: inset(25% 0 58% 0);
    transform: translate(-5px, -2px);
  }
  80% {
    clip-path: inset(54% 0 7% 0);
    transform: translate(2px, -4px);
  }
  100% {
    clip-path: inset(58% 0 43% 0);
    transform: translate(-2px, 2px);
  }
`;

interface Message {
  id?: string;
  message_id?: string;
  timestamp?: string;
  sender_id?: string;
  receiver_id?: string;
  content?: any;
  message_type?: string;
  type?: string;
  // Add fields for nested message structure
  message?: {
    sender_id?: string;
    receiver_id?: string;
    content?: any;
    timestamp?: string;
    message_id?: string;
  };
  data?: {
    message?: {
      sender_id?: string;
      receiver_id?: string;
      content?: any;
      timestamp?: string;
      message_id?: string;
    };
    timestamp?: string;
    sender_id?: string;
    receiver_id?: string;
    content?: any;
  };
}

export const MessageList: React.FC = () => {
  const { messages, agents } = useAgentStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [hoveredMessage, setHoveredMessage] = useState<string | null>(null);

  // Debug logging
  useEffect(() => {
    // More detailed message structure debugging
    if (messages && messages.length > 0) {
      const firstMsg = messages[0] as any; // Use type assertion to avoid TypeScript errors
      
      // Check for nested message structure
      if (firstMsg.data && firstMsg.data.message) {
        console.log('Nested message found in data.message:', JSON.stringify(firstMsg.data.message, null, 2));
      }
    }
  }, [agents, messages]);

  // Scroll to bottom when messages change
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const formatTimestamp = (timestamp?: string) => {
    if (!timestamp) return 'Unknown time';
    try {
    const date = new Date(timestamp);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch (e) {
      console.error('Error formatting timestamp:', e);
      return 'Invalid time';
    }
  };

  const getAgentIcon = (senderId?: string) => {
    if (!senderId) return <ComputerIcon sx={{ color: '#00FF41' }} />;
    
    // Check if it's a human/user
    const userId = localStorage.getItem('userId');
    if (userId === senderId) {
      return <PersonIcon sx={{ color: '#00FFFF' }} />;
    }
    
    // Find human agent
    let humanAgent = null;
    if (typeof agents === 'object') {
      // If agents is an object with values
      const agentValues = Object.values(agents);
      humanAgent = agentValues.find((agent: any) => 
        agent && agent.type && agent.type.toLowerCase() === 'human'
      );
    }
    
    if (humanAgent && humanAgent.id === senderId) {
      return <PersonIcon sx={{ color: '#00FFFF' }} />;
    }
    
    // Check agent type
    const agent = agents[senderId];
    if (!agent) return <ComputerIcon sx={{ color: '#00FF41' }} />;

    switch (agent.type && agent.type.toLowerCase()) {
      case 'system':
        return <MemoryIcon sx={{ color: '#00FF41' }} />;
      case 'analyst':
        return <CodeIcon sx={{ color: '#00FF41' }} />;
      default:
        return <ComputerIcon sx={{ color: '#00FF41' }} />;
    }
  };

  const renderMessageContent = (content: Message['content']) => {
    if (!content) return 'No content';
    
    // If content is a string, return it directly
    if (typeof content === 'string') {
      return content;
    }

    // If content has a text property, return just the text value
    if (content.text) {
      return content.text;
    }

    if (content.status) {
      return `Status: ${content.status}`;
    }

    // For other object structures, stringify them
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
                  color: 'rgba(0, 255, 65, 0.8)',
                  fontSize: '0.875rem',
                  fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                  letterSpacing: '0.03em',
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
              color: 'rgba(0, 255, 65, 0.8)',
              fontSize: '0.875rem',
              fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
              letterSpacing: '0.03em',
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
        position: 'relative',
        height: '100%', // Ensure the container takes full height
        '&::-webkit-scrollbar': {
          width: '8px',
        },
        '&::-webkit-scrollbar-track': {
          background: '#0D0208',
        },
        '&::-webkit-scrollbar-thumb': {
          backgroundColor: '#003B00',
          borderRadius: '4px',
          border: '1px solid #00FF41',
          '&:hover': {
            backgroundColor: '#00FF41',
          },
        },
        '&::before': {
          content: '""',
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          background: 'repeating-linear-gradient(0deg, rgba(0, 255, 65, 0.02) 0px, rgba(0, 255, 65, 0.02) 1px, transparent 1px, transparent 2px)',
          pointerEvents: 'none',
          opacity: 0.3,
          zIndex: 0,
        },
        '&::after': {
          content: '""',
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          background: 'linear-gradient(180deg, rgba(0, 0, 0, 0.7) 0%, transparent 5%, transparent 95%, rgba(0, 0, 0, 0.7) 100%)',
          pointerEvents: 'none',
          zIndex: 1,
        }
      }}
    >
      {messages.length === 0 ? (
        <Box sx={{ 
          display: 'flex', 
          flexDirection: 'column',
          justifyContent: 'center', 
          alignItems: 'center', 
          height: '100%',
          position: 'relative',
          zIndex: 2,
        }}>
          <MemoryIcon 
            sx={{ 
              fontSize: '3rem', 
              color: '#00FF41', 
              mb: 2,
              opacity: 0.7,
              animation: `${pulse} 3s infinite ease-in-out`,
            }} 
          />
          <Typography 
            variant="body1" 
            sx={{ 
              color: '#00FF41',
              fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
              letterSpacing: '0.05em',
              textAlign: 'center',
              position: 'relative',
              display: 'inline-block',
              '&::after': {
                content: '"|"',
                position: 'absolute',
                right: '-10px',
                color: '#00FF41',
                animation: `${blink} 1s step-end infinite`,
              }
            }}
          >
            NEURAL NETWORK INITIALIZED
          </Typography>
          <Typography 
            variant="body2" 
            sx={{ 
              color: 'rgba(0, 255, 65, 0.7)',
              fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
              letterSpacing: '0.05em',
              mt: 1,
              textAlign: 'center',
            }}
          >
            AWAITING INPUT SEQUENCE...
          </Typography>
        </Box>
      ) : (
        <Box sx={{ 
          display: 'flex', 
          flexDirection: 'column', 
          gap: 2, 
          width: '100%',
          minHeight: '100%',
          position: 'relative',
          zIndex: 2
        }}>
          {messages.map((msg: any, index: number) => {
            // Get a unique ID for the message
            const messageId = msg.id || msg.message_id || `msg-${index}`;
            
            // Safely extract sender and receiver IDs
            let senderId;
            let receiverId;
            
            // Check for WebSocket message format (data.message structure)
            if (msg.data && msg.data.message) {
              senderId = msg.data.message.sender_id;
              receiverId = msg.data.message.receiver_id;
            } 
            // Check for nested message format
            else if (msg.message) {
              senderId = msg.message.sender_id;
              receiverId = msg.message.receiver_id;
            } 
            // Check for direct format
            else {
              senderId = msg.sender_id;
              receiverId = msg.receiver_id;
            }
            
            // Get agent names safely
            const senderName = getAgentName(senderId, agents);
            const receiverName = getAgentName(receiverId, agents);

            // Extract message content safely
            let content;
            try {
              // Check for WebSocket message format
              if (msg.data && msg.data.message && msg.data.message.content) {
                const rawContent = msg.data.message.content;

                if (typeof rawContent === 'string') {
                  content = rawContent;
                } else if (typeof rawContent === 'object') {
                  if (rawContent.text) {
                    content = rawContent.text;
                  } else {
                    content = JSON.stringify(rawContent);
                  }
                }
              } 
              // Check for nested message format
              else if (msg.message && msg.message.content) {
                const rawContent = msg.message.content;

                if (typeof rawContent === 'string') {
                  content = rawContent;
                } else if (typeof rawContent === 'object') {
                  if (rawContent.text) {
                    content = rawContent.text;
                  } else {
                    content = JSON.stringify(rawContent);
                  }
                }
              } 
              // Check for direct format
              else if (msg.content) {
                const rawContent = msg.content;
                
                if (typeof rawContent === 'string') {
                  content = rawContent;
                } else if (typeof rawContent === 'object') {
                  if (rawContent.text) {
                    content = rawContent.text;
                  } else {
                    content = JSON.stringify(rawContent);
                  }
                }
              } else {
                console.log(`Message ${index} has no recognizable content structure`);
                content = 'No content';
              }
            } catch (e) {
              console.error(`Error extracting content for message ${index}:`, e);
              content = 'Error displaying message';
            }
            
            // Get timestamp
            const timestamp = msg.timestamp || 
              (msg.message && msg.message.timestamp) || 
              (msg.data && msg.data.timestamp) ||
              (msg.data && msg.data.message && msg.data.message.timestamp);
            
            const isOutgoing = senderId === localStorage.getItem('userId') || 
                              msg.type === 'outgoing' ||
                              Object.values(agents).find((a: any) => a.type === 'human')?.id === senderId;
            
            const isHovered = hoveredMessage === messageId;
          
          return (
            <Paper 
              key={index} 
              elevation={1}
                onMouseEnter={() => setHoveredMessage(messageId)}
                onMouseLeave={() => setHoveredMessage(null)}
              sx={{ 
                p: 2, 
                maxWidth: '80%', 
                  width: 'auto',
                  minWidth: '200px',
                alignSelf: isOutgoing ? 'flex-end' : 'flex-start',
                  backgroundColor: isOutgoing ? 'rgba(0, 150, 255, 0.1)' : 'rgba(0, 30, 0, 0.5)',
                  color: isOutgoing ? '#00FFFF' : '#00FF41',
                  borderRadius: '4px',
                  border: isOutgoing ? '1px solid rgba(0, 150, 255, 0.3)' : '1px solid rgba(0, 59, 0, 0.5)',
                  boxShadow: isHovered 
                    ? isOutgoing 
                      ? '0 0 15px rgba(0, 150, 255, 0.3), inset 0 0 5px rgba(0, 150, 255, 0.2)' 
                      : '0 0 15px rgba(0, 255, 65, 0.3), inset 0 0 5px rgba(0, 255, 65, 0.2)'
                    : 'none',
                  transition: 'all 0.3s ease',
                  position: 'relative',
                  zIndex: 2,
                  overflow: 'visible',
                  display: 'flex',
                  flexDirection: 'column',
                  height: 'auto',
                  ...(index % 5 === 1 && !isOutgoing ? {
                    borderLeft: '2px solid #FF8C00',
                    '&::before': {
                      background: 'linear-gradient(90deg, #FF8C00, rgba(0, 255, 65, 0.5), transparent) !important',
                    }
                  } : {}),
                  ...(index % 5 === 3 && !isOutgoing ? {
                    borderRight: '2px solid #0047AB',
                    '&::before': {
                      background: 'linear-gradient(90deg, transparent, rgba(0, 255, 65, 0.5), #0047AB) !important',
                    }
                  } : {}),
                  ...(index % 5 === 2 && isOutgoing ? {
                    borderLeft: '2px solid #0047AB',
                    '&::before': {
                      background: 'linear-gradient(90deg, #0047AB, rgba(0, 150, 255, 0.5), transparent) !important',
                    }
                  } : {}),
                  ...(index % 5 === 4 && isOutgoing ? {
                    borderRight: '2px solid #FF8C00',
                    '&::before': {
                      background: 'linear-gradient(90deg, transparent, rgba(0, 150, 255, 0.5), #FF8C00) !important',
                    }
                  } : {}),
                  '&::before': {
                    content: '""',
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '1px',
                    background: isOutgoing 
                      ? 'linear-gradient(90deg, transparent, rgba(0, 150, 255, 0.5), transparent)' 
                      : 'linear-gradient(90deg, transparent, rgba(0, 255, 65, 0.5), transparent)',
                    opacity: isHovered ? 1 : 0.5,
                    transition: 'opacity 0.3s ease',
                  },
                  '&::after': isHovered ? {
                    content: '""',
                    position: 'absolute',
                    top: '-100%',
                    left: 0,
                    width: '100%',
                    height: '300%',
                    background: isOutgoing 
                      ? 'linear-gradient(180deg, transparent 0%, rgba(0, 150, 255, 0.03) 50%, transparent 100%)' 
                      : 'linear-gradient(180deg, transparent 0%, rgba(0, 255, 65, 0.03) 50%, transparent 100%)',
                    animation: `${scanline} 2s linear infinite`,
                    pointerEvents: 'none',
                    zIndex: 0,
                  } : {},
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', mb: 1, gap: 1, width: '100%' }}>
                  <Box 
                    sx={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      justifyContent: 'center',
                      width: 28, 
                      height: 28, 
                      borderRadius: '50%',
                      backgroundColor: isOutgoing ? 'rgba(0, 150, 255, 0.1)' : 'rgba(0, 59, 0, 0.3)',
                      border: isOutgoing ? '1px solid rgba(0, 150, 255, 0.3)' : '1px solid rgba(0, 59, 0, 0.5)',
                      flexShrink: 0,
                      ...(index % 5 === 1 ? {
                        boxShadow: '0 0 5px #FF8C00',
                      } : {}),
                      ...(index % 5 === 3 ? {
                        boxShadow: '0 0 5px #0047AB',
                      } : {}),
                    }}
                  >
                    {getAgentIcon(senderId)}
                  </Box>
                  <Typography 
                    variant="subtitle2" 
                    fontWeight="bold"
                    sx={{ 
                      fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                      letterSpacing: '0.05em',
                      color: isOutgoing ? '#00FFFF' : '#00FF41',
                      textShadow: isOutgoing ? '0 0 5px rgba(0, 150, 255, 0.5)' : '0 0 5px rgba(0, 255, 65, 0.5)',
                      ...(index % 5 === 1 ? {
                        textShadow: '0 0 5px rgba(255, 140, 0, 0.5)',
                      } : {}),
                      ...(index % 5 === 3 ? {
                        textShadow: '0 0 5px rgba(0, 71, 171, 0.5)',
                      } : {}),
                    }}
                  >
                {senderName}
              </Typography>
                </Box>
                
                <Box sx={{ 
                  display: 'flex', 
                  flexDirection: 'column', 
                  flexGrow: 1, 
                  width: '100%',
                  alignSelf: 'stretch'
                }}>
                  <Typography 
                    variant="body1"
                    sx={{ 
                      fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                      letterSpacing: '0.03em',
                      color: isOutgoing ? 'rgba(0, 255, 255, 0.9)' : 'rgba(0, 255, 65, 0.9)',
                      ml: 4.5,
                      position: 'relative',
                      zIndex: 2,
                      wordBreak: 'break-word',
                      whiteSpace: 'pre-wrap',
                      display: 'block',
                      width: '100%',
                      '&::selection': {
                        backgroundColor: isOutgoing ? 'rgba(0, 150, 255, 0.3)' : 'rgba(0, 255, 65, 0.3)',
                        color: isOutgoing ? '#00FFFF' : '#00FF41',
                      },
                      ...(index % 5 === 1 && !isOutgoing ? {
                        '&::first-letter': {
                          color: 'rgba(255, 140, 0, 0.9)',
                        }
                      } : {}),
                      ...(index % 5 === 3 && !isOutgoing ? {
                        '&::first-letter': {
                          color: 'rgba(65, 105, 225, 0.9)',
                        }
                      } : {}),
                    }}
                  >
                    {content}
              </Typography>
              
                  {/* Render any secondary content like insights */}
                  {msg.content && typeof msg.content === 'object' && 
                    (msg.content.insights || msg.content.status) && 
                    renderSecondaryContent(msg.content)}
                </Box>
                
                <Typography 
                  variant="caption" 
                  sx={{ 
                    opacity: 0.7, 
                    display: 'block', 
                    textAlign: 'right', 
                    mt: 1,
                    fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                    letterSpacing: '0.03em',
                    color: isOutgoing ? 'rgba(0, 255, 255, 0.7)' : 'rgba(0, 255, 65, 0.7)',
                    alignSelf: 'flex-end',
                    width: '100%',
                    ...(index % 5 === 1 ? {
                      color: 'rgba(255, 140, 0, 0.7)',
                    } : {}),
                    ...(index % 5 === 3 ? {
                      color: 'rgba(65, 105, 225, 0.7)',
                    } : {}),
                  }}
                >
                  {formatTimestamp(timestamp)}
              </Typography>
            </Paper>
          );
          })}
          <div ref={messagesEndRef} />
        </Box>
      )}
    </Box>
  );
}; 