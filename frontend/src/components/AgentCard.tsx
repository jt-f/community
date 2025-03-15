import React, { useEffect, useState } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Chip,
  Box,
  LinearProgress,
  Tooltip,
  IconButton,
  CardActions,
  Divider,
  keyframes
} from '@mui/material';
import {
  Memory as MemoryIcon,
  Queue as QueueIcon,
  Update as UpdateIcon,
  Message as MessageIcon,
  Delete as DeleteIcon,
  Refresh as RefreshIcon,
  Code as CodeIcon
} from '@mui/icons-material';
import { useAgentStore } from '../store/agentStore';

// Update the interface to match what we have in the store
interface Agent {
  id: string;
  name: string;
  type: string;
  status: 'idle' | 'responding' | 'thinking';
  capabilities: string[];
  model?: string;
  provider?: string;
}

interface AgentCardProps {
  agent: Agent;
}

// Define keyframes for animations
const flicker = keyframes`
  0%, 100% { opacity: 1; }
  3% { opacity: 0.8; }
  6% { opacity: 1; }
  9% { opacity: 0.9; }
  12% { opacity: 1; }
  15% { opacity: 0.9; }
  18% { opacity: 1; }
  33% { opacity: 1; }
  36% { opacity: 0.9; }
  39% { opacity: 1; }
  100% { opacity: 1; }
`;

const pulse = keyframes`
  0%, 100% { opacity: 0.8; }
  50% { opacity: 1; }
`;

const thinkingPulse = keyframes`
  0%, 100% { opacity: 0.8; }
  50% { opacity: 1; }
`;

const respondingPulse = keyframes`
  0%, 100% { opacity: 0.8; }
  50% { opacity: 1; }
`;

const scanline = keyframes`
  0% { transform: translateY(-100%); }
  100% { transform: translateY(100%); }
`;

// Function to get animation settings based on status
const getStatusAnimation = (status: string) => {
  switch (status) {
    case 'thinking':
      return {
        animation: thinkingPulse,
        color: '#FF9800',
        scanlineColor: 'rgba(255, 152, 0, 0.1)',
        showAnimation: true
      };
    case 'responding':
      return {
        animation: respondingPulse,
        color: '#00FF41',
        scanlineColor: 'rgba(0, 255, 65, 0.1)',
        showAnimation: true
      };
    case 'idle':
      return {
        animation: 'none',
        color: '#00BB41',
        scanlineColor: 'rgba(0, 187, 65, 0.1)',
        showAnimation: false
      };
    default:
      return {
        animation: 'none',
        color: '#00BB41',
        scanlineColor: 'rgba(0, 187, 65, 0.1)',
        showAnimation: false
      };
  }
};

export const AgentCard: React.FC<AgentCardProps> = ({ agent }) => {
  const { sendMessage } = useAgentStore();
  const [isHovered, setIsHovered] = useState(false);
  const [randomDelay, setRandomDelay] = useState(0);
  
  useEffect(() => {
    // Set a random delay for animations to create a more organic feel
    setRandomDelay(Math.random() * 5);
  }, []);
  
  const handleMessageClick = () => {
    // Implement message sending logic
    console.log(`Send message to ${agent.name}`);
  };
  
  const handleDeleteClick = () => {
    // Implement agent deletion logic
    console.log(`Delete agent ${agent.name}`);
  };
  
  const handleRefreshClick = () => {
    // Implement agent refresh logic
    console.log(`Refresh agent ${agent.name}`);
  };
  
  console.log('provider:'+agent.provider);
  
  const statusSettings = getStatusAnimation(agent.status);
  
  return (
    <Card 
      sx={{ 
        height: '100%', 
        display: 'flex', 
        flexDirection: 'column',
        position: 'relative',
        backgroundColor: 'rgba(10, 10, 10, 0.8)',
        backdropFilter: 'blur(5px)',
        border: '1px solid #003B00',
        boxShadow: isHovered 
          ? '0 0 20px rgba(0, 255, 65, 0.4), inset 0 0 15px rgba(0, 255, 65, 0.2)' 
          : '0 0 15px rgba(0, 255, 65, 0.2), inset 0 0 10px rgba(0, 255, 65, 0.1)',
        transition: 'all 0.3s ease',
        overflow: 'hidden',
        transform: isHovered ? 'translateY(-2px)' : 'none',
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
        },
        '&::after': statusSettings.showAnimation ? {
          content: '""',
          position: 'absolute',
          top: '-100%',
          left: 0,
          width: '100%',
          height: '200%',
          background: `linear-gradient(180deg, transparent 0%, ${statusSettings.scanlineColor} 50%, transparent 100%)`,
          animation: `${scanline} 4s linear infinite`,
          animationDelay: `${randomDelay}s`,
          pointerEvents: 'none',
          zIndex: 2,
        } : {}
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <CardContent sx={{ 
        flexGrow: 1, 
        position: 'relative', 
        zIndex: 3, 
        p: 1.5, // Reduced padding
        '&:last-child': { pb: 1.5 } // Override default padding
      }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 0.5 }}>
          <Typography 
            variant="subtitle1" // Smaller font size
            component="h2"
            sx={{ 
              fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
              color: '#00FF41',
              textShadow: isHovered ? '0 0 10px #00FF41' : '0 0 5px #00FF41',
              letterSpacing: '0.05em',
              animation: `${flicker} ${5 + randomDelay}s infinite`,
              display: 'flex',
              alignItems: 'center',
              gap: '4px', // Reduced gap
              fontSize: '0.9rem', // Smaller font size
              lineHeight: 1.2 // Tighter line height
            }}
          >
            <CodeIcon sx={{ fontSize: '0.9em', opacity: 0.8 }} />
            {agent.name}
          </Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
            <Chip 
              label={agent.status} 
              color={
                agent.status === 'responding' ? 'success' : 
                agent.status === 'thinking' ? 'warning' : 'default'
              }
              size="small"
              sx={{
                fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                letterSpacing: '0.05em',
                animation: agent.status !== 'idle' ? `${statusSettings.animation} 2s infinite` : 'none',
                textShadow: `0 0 5px ${statusSettings.color}`,
                border: '1px solid #003B00',
                background: agent.status === 'responding' 
                  ? 'linear-gradient(to right, #003B00, rgba(0, 59, 0, 0.7))' 
                  : agent.status === 'thinking'
                    ? 'linear-gradient(to right, #3A2F0B, rgba(58, 47, 11, 0.7))'
                    : 'linear-gradient(to right, #002B00, rgba(0, 43, 0, 0.7))',
                boxShadow: `0 0 5px ${statusSettings.color}`,
                height: '20px', // Smaller height
                '& .MuiChip-label': {
                  padding: '0 6px', // Reduced padding
                  fontSize: '0.65rem' // Smaller font
                }
              }}
            />
            {(agent.model || agent.provider) && (
              <Typography 
                variant="caption" 
                color="text.secondary" 
                sx={{ 
                  mt: 0.25, // Reduced margin
                  textAlign: 'right',
                  fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                  color: 'rgba(0, 255, 65, 0.7)',
                  textShadow: '0 0 3px rgba(0, 255, 65, 0.5)',
                  letterSpacing: '0.05em',
                  fontSize: '0.65rem', // Smaller font
                  lineHeight: 1.1 // Tighter line height
                }}
              >
                {agent.model && `${agent.model}`}{agent.model && agent.provider && ' • '}{agent.provider && `${agent.provider}`}
              </Typography>
            )}
          </Box>
        </Box>
        
        <Box sx={{ mt: 1 }}>
          <Typography 
            variant="caption" 
            color="text.secondary"
            sx={{ 
              fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
              color: 'rgba(0, 255, 65, 0.7)',
              textShadow: '0 0 2px rgba(0, 255, 65, 0.3)',
              letterSpacing: '0.05em',
              fontSize: '0.65rem', // Smaller font
              lineHeight: 1.1 // Tighter line height
            }}
          >
            Capabilities:
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.25, mt: 0.25 }}>
            {agent.capabilities.map((cap, index) => (
              <Chip
                key={index}
                label={cap}
                size="small"
                variant="outlined"
                sx={{ 
                  fontSize: '0.6rem', // Smaller font
                  fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                  letterSpacing: '0.05em',
                  border: '1px solid #003B00',
                  background: 'transparent',
                  color: '#00FF41',
                  textShadow: '0 0 3px rgba(0, 255, 65, 0.5)',
                  transition: 'all 0.3s ease',
                  height: '18px', // Smaller height
                  '& .MuiChip-label': {
                    padding: '0 4px', // Reduced padding
                  },
                  '&:hover': {
                    boxShadow: '0 0 5px #00FF41',
                    borderColor: '#00FF41',
                  }
                }}
              />
            ))}
          </Box>
        </Box>

        <Typography 
          color="text.secondary" 
          sx={{ 
            fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
            color: 'rgba(0, 255, 65, 0.7)',
            textShadow: '0 0 2px rgba(0, 255, 65, 0.3)',
            letterSpacing: '0.05em',
            mt: 0.5, // Reduced margin
            fontSize: '0.65rem', // Smaller font
            lineHeight: 1.1 // Tighter line height
          }}
        >
          Type: {agent.type}
        </Typography>
        
        {/* Add a subtle progress bar for visual effect */}
        <Box sx={{ mt: 1, mb: 0 }}>
          <LinearProgress 
            variant="indeterminate" 
            sx={{
              height: '2px',
              borderRadius: '1px',
              backgroundColor: '#003B00',
              '.MuiLinearProgress-bar': {
                background: 'linear-gradient(90deg, #003B00, #00FF41, #39FF14)',
                boxShadow: '0 0 5px #00FF41',
              }
            }}
          />
        </Box>
      </CardContent>
      
      <CardActions sx={{ 
        justifyContent: 'flex-end', 
        borderTop: '1px solid rgba(0, 59, 0, 0.5)',
        background: 'rgba(0, 10, 0, 0.3)',
        position: 'relative',
        zIndex: 3,
        p: 0.5, // Reduced padding
        minHeight: '36px' // Smaller height
      }}>
        <IconButton 
          size="small" 
          onClick={handleMessageClick} 
          title="Send Message"
          sx={{
            color: '#00FF41',
            transition: 'all 0.3s ease',
            padding: '4px', // Smaller padding
            '&:hover': {
              backgroundColor: 'rgba(0, 255, 65, 0.1)',
              transform: 'scale(1.1)',
              boxShadow: '0 0 10px #00FF41',
            }
          }}
        >
          <MessageIcon fontSize="small" />
        </IconButton>
        <IconButton 
          size="small" 
          onClick={handleRefreshClick} 
          title="Refresh Agent"
          sx={{
            color: '#00FF41',
            transition: 'all 0.3s ease',
            padding: '4px', // Smaller padding
            '&:hover': {
              backgroundColor: 'rgba(0, 255, 65, 0.1)',
              transform: 'scale(1.1)',
              boxShadow: '0 0 10px #00FF41',
            }
          }}
        >
          <RefreshIcon fontSize="small" />
        </IconButton>
        <IconButton 
          size="small" 
          onClick={handleDeleteClick} 
          title="Delete Agent"
          sx={{
            color: '#00FF41',
            transition: 'all 0.3s ease',
            padding: '4px', // Smaller padding
            '&:hover': {
              backgroundColor: 'rgba(255, 7, 58, 0.1)',
              transform: 'scale(1.1)',
              boxShadow: '0 0 10px #FF073A',
              color: '#FF073A',
            }
          }}
        >
          <DeleteIcon fontSize="small" />
        </IconButton>
      </CardActions>
    </Card>
  );
}; 