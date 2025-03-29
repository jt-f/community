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
  IconButton,
  Tooltip,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from '@mui/material';
import { 
  Computer as ComputerIcon, 
  Person as PersonIcon,
  Code as CodeIcon,
  Memory as MemoryIcon,
  Reply as ReplyIcon,
  DeleteSweep as DeleteSweepIcon,
} from '@mui/icons-material';
import { useAgentStore } from '../store/agentStore';
import { useMessageStore, Message as MessageType } from '../store/messageStore';
import { getAgentName } from '../utils/agentUtils';
import { getReplyStyles, enhanceMessageWithReplyData } from '../utils/messageReplyUtils';

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

// Function to trigger a reply event
const triggerReplyTo = (messageId: string) => {
  // Create and dispatch a custom event
  const event = new CustomEvent('replyToMessage', {
    detail: { messageId }
  });
  window.dispatchEvent(event);
};

export const MessageList: React.FC = () => {
  const { agents } = useAgentStore();
  const { messages, messagesByID, getEffectiveReceiver, clearHistory } = useMessageStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [hoveredMessage, setHoveredMessage] = useState<string | null>(null);
  const [confirmDialogOpen, setConfirmDialogOpen] = useState(false);

  // Debug logging
  useEffect(() => {
    // More detailed message structure debugging
    if (messages && messages.length > 0) {
      console.log('Message store contains', messages.length, 'messages');
    }
  }, [messages]);

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

  const renderMessageContent = (content: MessageType['content']) => {
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

  const renderSecondaryContent = (content: MessageType['content']) => {
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

  // Handler for clearing message history
  const handleClearHistory = () => {
    clearHistory();
    setConfirmDialogOpen(false);
  };

  return (
    <Box 
      sx={{ 
        flexGrow: 1, 
        overflow: 'auto',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        p: 2,
        gap: 2,
        backgroundColor: 'rgba(0, 10, 2, 0.95)',
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
          height: '100%',
          background: 'linear-gradient(180deg, rgba(0, 0, 0, 0.7) 0%, transparent 5%, transparent 95%, rgba(0, 0, 0, 0.7) 100%)',
          pointerEvents: 'none',
          zIndex: 1,
        }
      }}
    >
      {/* Clear History Button */}
      <Box 
        sx={{ 
          position: 'sticky', 
          top: 0, 
          p: 1, 
          zIndex: 3, 
          display: 'flex', 
          justifyContent: 'flex-end',
          backgroundColor: 'rgba(10, 10, 10, 0.8)',
          borderBottom: '1px solid #003B00',
          boxShadow: '0 0 10px rgba(0, 255, 65, 0.2)'
        }}
      >
        <Button
          size="small"
          variant="outlined"
          startIcon={<DeleteSweepIcon />}
          onClick={() => setConfirmDialogOpen(true)}
          sx={{
            color: '#FF5252',
            borderColor: 'rgba(255, 82, 82, 0.5)',
            fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
            letterSpacing: '0.05em',
            '&:hover': {
              borderColor: '#FF5252',
              backgroundColor: 'rgba(255, 82, 82, 0.1)',
            },
          }}
        >
          PURGE DATA
        </Button>
      </Box>

      {/* Confirmation Dialog */}
      <Dialog
        open={confirmDialogOpen}
        onClose={() => setConfirmDialogOpen(false)}
        PaperProps={{
          sx: {
            backgroundColor: 'rgba(10, 10, 10, 0.95)',
            border: '1px solid #003B00',
            boxShadow: '0 0 20px rgba(0, 255, 65, 0.3)',
            color: '#00FF41',
            fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
          }
        }}
      >
        <DialogTitle sx={{ borderBottom: '1px solid #003B00' }}>
          CONFIRM DATA PURGE
        </DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ color: '#00FF41', my: 2 }}>
            WARNING: ALL MESSAGE DATA WILL BE PERMANENTLY ERASED FROM LOCAL STORAGE. THIS ACTION CANNOT BE UNDONE.
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ borderTop: '1px solid #003B00', p: 2 }}>
          <Button 
            onClick={() => setConfirmDialogOpen(false)}
            sx={{ 
              color: '#00FF41',
              '&:hover': { backgroundColor: 'rgba(0, 255, 65, 0.1)' },
            }}
          >
            CANCEL
          </Button>
          <Button 
            onClick={handleClearHistory}
            sx={{ 
              color: '#FF5252',
              '&:hover': { backgroundColor: 'rgba(255, 82, 82, 0.1)' },
            }}
            autoFocus
          >
            CONFIRM PURGE
          </Button>
        </DialogActions>
      </Dialog>

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
          {messages.map((originalMsg: MessageType, index: number) => {
            // Enhance message with reply metadata
            const msg = enhanceMessageWithReplyData(originalMsg);
            
            // Get sender and receiver info
            const senderId = msg.sender_id;
            const senderName = getAgentName(senderId, agents);
            
            // Get the effective receiver (accounts for broadcast vs reply relationships)
            const effectiveReceiverId = getEffectiveReceiver(msg);
            const receiverName = getAgentName(effectiveReceiverId, agents);
            
            // Get human agent for determining if message is outgoing
            const humanAgent = Object.values(agents).find((a: any) => 
              a.type === 'human'
            );
            
            // Determine if message is outgoing
            const isOutgoing = msg.is_outgoing || senderId === humanAgent?.id;
            
            // Format content
            const content = typeof msg.content.text === 'string' 
              ? msg.content.text 
              : renderMessageContent(msg.content);
            
            const timestamp = msg.timestamp;
            const messageId = msg.message_id;
            const isHovered = hoveredMessage === messageId;
            
            // Get reply-specific styles
            const replyStyles = getReplyStyles(msg, index);
            
            // Add debug logging for the most recent message
            if (index === messages.length - 1) {
              console.log('DEBUG - Latest message:', {
                messageId,
                senderId,
                senderName,
                receiverId: msg.receiver_id,
                effectiveReceiverId,
                receiverName,
                inReplyTo: msg.in_reply_to,
                replyDepth: msg.replyDepth,
                hasReplies: msg.hasReplies,
                originalSender: msg.in_reply_to ? messagesByID[msg.in_reply_to]?.sender_id : undefined,
                isOutgoing
              });
            }
          
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
                  // Apply reply-specific styles to the Paper component
                  ...replyStyles.paper,
                  ...(msg.isReply && {
                    // Add small arrow indicator for replies
                    '&::before': {
                      content: '""',
                      position: 'absolute',
                      top: '10px',
                      left: isOutgoing ? 'auto' : '-10px',
                      right: isOutgoing ? '-10px' : 'auto',
                      width: '0',
                      height: '0',
                      borderTop: '5px solid transparent',
                      borderBottom: '5px solid transparent',
                      borderLeft: isOutgoing ? 'none' : `5px solid ${msg.replyDepth > 1 ? 'rgba(255, 140, 0, 0.8)' : 'rgba(0, 255, 65, 0.8)'}`,
                      borderRight: isOutgoing ? `5px solid ${msg.replyDepth > 1 ? 'rgba(0, 71, 171, 0.8)' : 'rgba(0, 150, 255, 0.8)'}` : 'none',
                    }
                  }),
                  // Add style variations based on message position
                  ...(index % 5 === 1 && !isOutgoing ? {
                    borderLeft: msg.isReply ? 'none' : '2px solid #FF8C00',
                    '&::after': {
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
                      // Add reply chain indicator glow if part of a chain
                      ...(msg.hasReplies && {
                        boxShadow: isOutgoing 
                          ? '0 0 8px rgba(0, 150, 255, 0.7)' 
                          : '0 0 8px rgba(0, 255, 65, 0.7)',
                      }),
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
                      // Apply reply-specific styles to the sender name
                      ...replyStyles.sender,
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
                  
                  {/* Show recipient info */}
                  <Box sx={{ display: 'flex', alignItems: 'center', ml: 2 }}>
                    <Typography 
                      variant="caption" 
                      sx={{ 
                        color: isOutgoing ? 'rgba(0, 255, 255, 0.8)' : 'rgba(0, 255, 65, 0.8)',
                        fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                        letterSpacing: '0.05em',
                        ml: 0.5,
                        fontSize: '0.7rem',
                        opacity: 0.9,
                      }}
                    >
                      {(() => {
                        // If this is a reply, show "REPLY TO: [original sender]" instead
                        if (msg.isReply && msg.in_reply_to) {
                          const originalMsg = messagesByID[msg.in_reply_to];
                          if (originalMsg) {
                            const originalSenderName = getAgentName(originalMsg.sender_id, agents);
                            return `REPLY TO: ${originalSenderName}`;
                          }
                        }
                        
                        // If no effective receiver, show unknown
                        if (!effectiveReceiverId) return 'TO: UNKNOWN';
                        
                        // If it's explicitly a broadcast with no specific target
                        if (effectiveReceiverId === 'broadcast') return 'TO: ALL AGENTS';
                        
                        // If receiver is a human agent, show their name
                        const isHumanReceiver = Object.values(agents).some((a: any) => 
                          a.type === 'human' && a.id === effectiveReceiverId
                        );
                        if (isHumanReceiver) return `TO: ${receiverName}`;
                        
                        // Otherwise show the agent name or ID
                        return `TO: ${receiverName || effectiveReceiverId}`;
                      })()}
                    </Typography>
                  </Box>
                  
                  {/* Add reply button */}
                  <Box sx={{ ml: 'auto' }}>
                    <Tooltip title="Reply to this message">
                      <IconButton
                        size="small"
                        onClick={() => triggerReplyTo(messageId)}
                        sx={{
                          color: isOutgoing ? 'rgba(0, 150, 255, 0.7)' : 'rgba(0, 255, 65, 0.7)',
                          padding: '4px',
                          opacity: isHovered ? 1 : 0,
                          transition: 'opacity 0.3s ease',
                          '&:hover': {
                            backgroundColor: isOutgoing ? 'rgba(0, 150, 255, 0.1)' : 'rgba(0, 255, 65, 0.1)',
                            color: isOutgoing ? '#00FFFF' : '#00FF41',
                          }
                        }}
                      >
                        <ReplyIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Box>
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
                      // Apply reply-specific styles to the message content
                      ...replyStyles.content,
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
                  
                  {/* Add small timestamp */}
                  <Typography
                    variant="caption"
                    sx={{
                      color: isOutgoing ? 'rgba(0, 255, 255, 0.5)' : 'rgba(0, 255, 65, 0.5)',
                      fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                      fontSize: '0.6rem',
                      textAlign: 'right',
                      mt: 1,
                      opacity: isHovered ? 0.8 : 0.5,
                      transition: 'opacity 0.3s ease',
                    }}
                  >
                    {/* Format the timestamp to show just time if today, date+time if older */}
                    {(() => {
                      try {
                        const date = new Date(timestamp);
                        const now = new Date();
                        const isToday = date.toDateString() === now.toDateString();
                        return isToday 
                          ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                          : date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                      } catch (e) {
                        return timestamp || 'Unknown time';
                      }
                    })()}
                  </Typography>
                </Box>
              </Paper>
            );
          })}
          <div ref={messagesEndRef} />
        </Box>
      )}
    </Box>
  );
}; 