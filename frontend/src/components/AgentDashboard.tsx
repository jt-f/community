import React, { useState, useEffect, useRef } from 'react';
import { Box, Button, Typography, Grid, Paper, keyframes, Divider } from '@mui/material';
import { 
  Add as AddIcon, 
  Memory as MemoryIcon,
  Code as CodeIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon
} from '@mui/icons-material';
import { AgentCard } from './AgentCard';
import { AgentCreationForm } from './AgentCreationForm';
import { useAgentStore } from '../store/agentStore';
import { useMessageStore, Message } from '../store/messageStore';

// Define keyframes for animations
const pulse = keyframes`
  0%, 100% { opacity: 0.8; }
  50% { opacity: 1; }
`;

const scanline = keyframes`
  0% { transform: translateY(-100%); }
  100% { transform: translateY(100%); }
`;

const flicker = keyframes`
  0%, 100% { opacity: 1; }
  3% { opacity: 0.8; }
  6% { opacity: 1; }
  9% { opacity: 0.9; }
  12% { opacity: 1; }
`;

// Animation for communication lines
const communicationPulse = keyframes`
  0% { opacity: 0; stroke-dashoffset: 100; }
  20% { opacity: 0.8; stroke-dashoffset: 75; }
  80% { opacity: 0.6; stroke-dashoffset: 25; }
  100% { opacity: 0; stroke-dashoffset: 0; }
`;

// Animation for dots at endpoints
const endpointPulse = keyframes`
  0% { r: 2; opacity: 1; }
  50% { r: 4; opacity: 0.8; }
  100% { r: 2; opacity: 0; }
`;

// Interface for agent position in the UI
interface AgentPosition {
  id: string;
  element: HTMLElement | null;
  rect: DOMRect | null;
}

// Interface for communication lines
interface CommunicationLine {
  id: string;
  senderId: string;
  receiverId: string;
  timestamp: number;
  path: string;
  color: string;
}

// Add a type for message objects to handle the nested structure properly
interface MessageObject {
  id?: string;
  message_id?: string;
  timestamp?: string;
  sender_id?: string;
  receiver_id?: string;
  in_reply_to?: string;
  content?: any;
  message_type?: string;
  type?: string;
  message?: {
    sender_id?: string;
    receiver_id?: string;
    in_reply_to?: string;
    message_id?: string;
    content?: any;
    timestamp?: string;
  };
  data?: {
    message?: {
      sender_id?: string;
      receiver_id?: string;
      in_reply_to?: string;
      message_id?: string;
      content?: any;
      timestamp?: string;
    };
    timestamp?: string;
    sender_id?: string;
    receiver_id?: string;
    content?: any;
  };
}

export const AgentDashboard: React.FC = () => {
  const { agents, messages } = useAgentStore();
  const [showCreationForm, setShowCreationForm] = useState(false);
  const [randomDelay, setRandomDelay] = useState(0);
  const dashboardRef = useRef<HTMLDivElement>(null);
  const [agentPositions, setAgentPositions] = useState<Record<string, AgentPosition>>({});
  const [communicationLines, setCommunicationLines] = useState<CommunicationLine[]>([]);
  
  // Generate a unique ID for communication lines
  const generateLineId = () => `line-${Date.now()}-${Math.floor(Math.random() * 1000)}`;

  useEffect(() => {
    // Set a random delay for animations to create a more organic feel
    setRandomDelay(Math.random() * 5);
  }, []);
  
  // Track agent card positions
  useEffect(() => {
    const updateAgentPositions = () => {
      const positions: Record<string, AgentPosition> = {};
      Object.keys(agents).forEach(agentId => {
        const element = document.getElementById(`agent-card-${agentId}`);
        if (element) {
          const rect = element.getBoundingClientRect();
          positions[agentId] = { id: agentId, element, rect };
        }
      });
      setAgentPositions(positions);
    };

    // Update immediately and then after a short delay to ensure DOM is fully rendered
    updateAgentPositions();
    const timer = setTimeout(updateAgentPositions, 500);
    
    // Update positions when window is resized
    window.addEventListener('resize', updateAgentPositions);

    return () => {
      window.removeEventListener('resize', updateAgentPositions);
      clearTimeout(timer);
    };
  }, [agents, showCreationForm]);

  // Watch for new messages to create communication lines
  useEffect(() => {
    if (messages.length === 0 || Object.keys(agentPositions).length === 0) return;

    // Check the latest message
    const latestMessage = messages[messages.length - 1] as MessageObject;
    
    // Extract sender and receiver IDs
    let senderId, receiverId, inReplyTo;
    
    // Get sender ID
    if (latestMessage.data?.message?.sender_id) {
      senderId = latestMessage.data.message.sender_id;
      inReplyTo = latestMessage.data.message.in_reply_to;
    } else if (latestMessage.message?.sender_id) {
      senderId = latestMessage.message.sender_id;
      inReplyTo = latestMessage.message.in_reply_to;
    } else {
      senderId = latestMessage.sender_id;
      inReplyTo = latestMessage.in_reply_to;
    }
    
    // Get receiver ID
    if (latestMessage.data?.message?.receiver_id) {
      receiverId = latestMessage.data.message.receiver_id;
    } else if (latestMessage.message?.receiver_id) {
      receiverId = latestMessage.message.receiver_id;
    } else {
      receiverId = latestMessage.receiver_id;
    }

    // If this is a broadcast message that's replying to another message,
    // try to find the original message's sender to use as the receiver
    let effectiveReceiverId = receiverId;
    if (receiverId === 'broadcast' && inReplyTo) {
      // Find the original message this is replying to
      const originalMessage = messages.find((m: any) => 
        m.message_id === inReplyTo || 
        m.message?.message_id === inReplyTo || 
        m.data?.message?.message_id === inReplyTo
      );
      
      if (originalMessage) {
        const originalSenderId = originalMessage.sender_id || 
                               originalMessage.message?.sender_id || 
                               originalMessage.data?.message?.sender_id;
        
        if (originalSenderId && originalSenderId !== senderId) {
          effectiveReceiverId = originalSenderId;
          console.log(`Found original sender ${originalSenderId} for reply message`);
        }
      }
    }

    console.log(`Drawing line: ${senderId} → ${effectiveReceiverId}`);
    console.log(`Agent positions available: ${Object.keys(agentPositions).join(', ')}`);

    // Only create a line if we have both sender and receiver and they're not the same
    if (
      senderId && 
      effectiveReceiverId && 
      senderId !== effectiveReceiverId && 
      agentPositions[senderId] && 
      agentPositions[effectiveReceiverId]
    ) {
      const senderRect = agentPositions[senderId].rect;
      const receiverRect = agentPositions[effectiveReceiverId].rect;
      
      if (senderRect && receiverRect && dashboardRef.current) {
        // Calculate center points of agent cards
        const dashboardRect = dashboardRef.current.getBoundingClientRect();
        
        // Adjust positions relative to the dashboard
        const x1 = senderRect.left + senderRect.width / 2 - dashboardRect.left;
        const y1 = senderRect.top + senderRect.height / 2 - dashboardRect.top;
        const x2 = receiverRect.left + receiverRect.width / 2 - dashboardRect.left;
        const y2 = receiverRect.top + receiverRect.height / 2 - dashboardRect.top;
        
        console.log(`Drawing path from (${x1},${y1}) to (${x2},${y2})`);
        
        // Create bezier curve path
        const path = `M ${x1} ${y1} C ${(x1 + x2) / 2} ${y1}, ${(x1 + x2) / 2} ${y2}, ${x2} ${y2}`;
        
        // Determine color based on message or random
        let color;
        if (senderId.startsWith('user-')) {
          color = '#00FFFF'; // Cyan for user messages
        } else if (effectiveReceiverId.startsWith('user-')) {
          color = '#00FF41'; // Green for responses to user
        } else {
          // Random from a set of colors for agent-to-agent communication
          const colors = ['#FF8C00', '#0047AB', '#9400D3', '#FF1493'];
          color = colors[Math.floor(Math.random() * colors.length)];
        }
        
        // Add new communication line
        const newLine: CommunicationLine = {
          id: generateLineId(),
          senderId,
          receiverId: effectiveReceiverId,
          timestamp: Date.now(),
          path,
          color
        };
        
        setCommunicationLines(prev => [...prev, newLine]);
        console.log(`Added communication line: ${newLine.id}`);
        
        // Remove line after animation finishes (3 seconds)
        setTimeout(() => {
          setCommunicationLines(prev => prev.filter(line => line.id !== newLine.id));
        }, 3000);
      }
    }
  }, [messages, agentPositions]);
  
  const getMessageStyle = (message: Message) => {
    const senderId = message.sender_id;
    const effectiveReceiverId = message.receiver_id === 'broadcast' ? 'all' : message.receiver_id;
    const senderAgent = agents[senderId];
    const receiverAgent = agents[effectiveReceiverId];

    if (senderAgent && senderAgent.type.toLowerCase() === 'human') {
      return { backgroundColor: 'rgba(0, 255, 65, 0.1)' };
    } else if (receiverAgent && receiverAgent.type.toLowerCase() === 'human') {
      return { backgroundColor: 'rgba(255, 140, 0, 0.1)' };
    }
    return {};
  };

  return (
    <Box 
      ref={dashboardRef}
      sx={{ 
        p: 3,
        position: 'relative',
        minHeight: '100vh',
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
      }}
    >
      {/* Communication lines SVG layer */}
      <svg 
        style={{ 
          position: 'fixed', 
          top: 0, 
          left: 0, 
          width: '100vw', 
          height: '100vh', 
          pointerEvents: 'none',
          zIndex: 1000, // Very high z-index to ensure it's on top
        }}
      >
        {communicationLines.map(line => (
          <React.Fragment key={line.id}>
            {/* The connection path */}
            <path
              d={line.path}
              fill="none"
              stroke={line.color}
              strokeWidth={3} // Increase stroke width
              strokeDasharray="10"
              strokeLinecap="round"
              style={{
                animation: `${communicationPulse} 3s forwards`,
                opacity: 0.8
              }}
            />
            {/* Add glowing effect */}
            <path
              d={line.path}
              fill="none"
              stroke={line.color}
              strokeWidth={8} // Increase glow width
              strokeLinecap="round"
              style={{
                animation: `${communicationPulse} 3s forwards`,
                opacity: 0.3,
                filter: 'blur(6px)' // Increase blur for more glow
              }}
            />
            {/* Add endpoint markers */}
            <circle
              cx={line.path.split(' ')[1]} // Extract x1 from path
              cy={line.path.split(' ')[2]} // Extract y1 from path
              r="4"
              fill={line.color}
              style={{
                filter: `drop-shadow(0 0 3px ${line.color})`,
                opacity: 0.8
              }}
            />
            <circle
              cx={line.path.split(' ')[line.path.split(' ').length - 2]} // Extract x2 from path
              cy={line.path.split(' ')[line.path.split(' ').length - 1]} // Extract y2 from path
              r="4"
              fill={line.color}
              style={{
                filter: `drop-shadow(0 0 3px ${line.color})`,
                opacity: 0.8
              }}
            />
          </React.Fragment>
        ))}
      </svg>
      
      <Box 
        sx={{ 
          display: 'flex', 
          justifyContent: 'center', 
          alignItems: 'center', 
          mb: 3,
          position: 'relative',
          zIndex: 1,
          width: '100%'
        }}
      >
        <Button 
          variant="contained" 
          startIcon={showCreationForm ? <ExpandLessIcon /> : <AddIcon />}
          onClick={() => setShowCreationForm(!showCreationForm)}
          fullWidth
          sx={{
            backgroundColor: 'rgba(0, 59, 0, 0.7)',
            color: '#00FF41',
            fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            border: '1px solid #003B00',
            boxShadow: '0 0 10px rgba(0, 255, 65, 0.2)',
            transition: 'all 0.3s ease',
            position: 'relative',
            overflow: 'hidden',
            maxWidth: '100%',
            py: 1.2,
            '&:hover': {
              backgroundColor: 'rgba(0, 59, 0, 0.9)',
              boxShadow: '0 0 15px rgba(0, 255, 65, 0.4)',
              '&::after': {
                opacity: 0.2,
              }
            },
            '&::before': {
              content: '""',
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '1px',
              background: 'linear-gradient(90deg, transparent, #00FF41, transparent)',
            },
            '&::after': {
              content: '""',
              position: 'absolute',
              top: '-100%',
              left: 0,
              width: '100%',
              height: '300%',
              background: 'linear-gradient(180deg, transparent, rgba(0, 255, 65, 0.1), transparent)',
              opacity: 0,
              transition: 'opacity 0.3s ease',
            }
          }}
        >
          {showCreationForm ? 'Collapse Interface' : 'Initialize New Agent'}
        </Button>
      </Box>
      
      {showCreationForm && (
        <Box 
          sx={{ 
            mb: 4, 
            position: 'relative',
            '&::before': {
              content: '""',
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              background: 'repeating-linear-gradient(0deg, rgba(0, 255, 65, 0.03) 0px, rgba(0, 255, 65, 0.03) 1px, transparent 1px, transparent 2px)',
              pointerEvents: 'none',
              opacity: 0.3,
              zIndex: 0,
            },
          }}
        >
          <AgentCreationForm onAgentCreated={() => setShowCreationForm(false)} />
        </Box>
      )}
      
      <Divider 
        sx={{ 
          mb: 3, 
          borderColor: 'rgba(0, 59, 0, 0.7)',
          '&::before, &::after': {
            borderColor: 'rgba(0, 59, 0, 0.7)',
          },
          position: 'relative',
          '&::after': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '1px',
            background: 'linear-gradient(90deg, transparent, rgba(0, 255, 65, 0.3), transparent)',
          }
        }} 
      />
      
      <Box sx={{ position: 'relative', zIndex: 1 }}>
        <Grid container spacing={1.5}>
          {Object.values(agents).map((agent, index) => (
            <Grid 
              item 
              xs={12} sm={6} md={4} 
              key={agent.id}
              sx={{ 
                mb: 0.5,
                position: 'relative',
                transition: 'all 0.3s ease',
                '&:hover': {
                  transform: 'translateY(-3px)',
                  zIndex: 10
                }
              }}
            >
              <div id={`agent-card-${agent.id}`}>
                <AgentCard agent={agent} />
              </div>
            </Grid>
          ))}
          
          {Object.keys(agents).length === 0 && (
            <Grid item xs={12}>
              <Paper 
                sx={{ 
                  p: 4, 
                  textAlign: 'center',
                  backgroundColor: 'rgba(10, 10, 10, 0.8)',
                  backdropFilter: 'blur(5px)',
                  border: '1px solid #003B00',
                  boxShadow: '0 0 15px rgba(0, 255, 65, 0.2), inset 0 0 10px rgba(0, 255, 65, 0.1)',
                  position: 'relative',
                  overflow: 'hidden',
                  '&::before': {
                    content: '""',
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '2px',
                    background: 'linear-gradient(90deg, transparent, #00FF41, transparent)',
                  },
                  '&::after': {
                    content: '""',
                    position: 'absolute',
                    top: 0,
                    left: '-100%',
                    width: '100%',
                    height: '100%',
                    background: 'linear-gradient(90deg, transparent, rgba(0, 255, 65, 0.05), transparent)',
                    animation: `${scanline} 3s linear infinite`,
                    animationDelay: `${randomDelay}s`,
                  }
                }}
              >
                <CodeIcon 
                  sx={{ 
                    fontSize: '3rem', 
                    color: '#00FF41', 
                    opacity: 0.7, 
                    mb: 2,
                    animation: `${pulse} 3s infinite ease-in-out`,
                  }} 
                />
                <Typography 
                  variant="body1" 
                  sx={{ 
                    color: '#00FF41',
                    fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                    letterSpacing: '0.05em',
                    textShadow: '0 0 5px rgba(0, 255, 65, 0.5)',
                  }}
                >
                  NO ACTIVE NEURAL AGENTS DETECTED
                </Typography>
                <Typography 
                  variant="body2" 
                  sx={{ 
                    color: 'rgba(0, 255, 65, 0.7)',
                    fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                    letterSpacing: '0.05em',
                    mt: 1,
                  }}
                >
                  INITIALIZE A NEW AGENT TO ESTABLISH NEURAL LINK
                </Typography>
              </Paper>
            </Grid>
          )}
        </Grid>
      </Box>
    </Box>
  );
}; 