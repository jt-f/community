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
import { Agent } from '../types/agent';

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
        color: '#FFA726',  // Warm orange
        scanlineColor: 'rgba(255, 167, 38, 0.15)',
        borderColor: '#FF9800',
        gradientStart: '#2C1810',  // Deep warm brown
        gradientEnd: 'rgba(44, 24, 16, 0.85)',
        glowColor: 'rgba(255, 152, 0, 0.45)',
        textColor: '#FFB74D',  // Light orange
        progressBarColors: 'linear-gradient(90deg, #2C1810, #FFA726, #FFB74D)',
        showAnimation: true,
        backgroundOpacity: 0.92,
        backgroundPattern: `repeating-linear-gradient(
          45deg,
          rgba(255, 167, 38, 0.1) 0px,
          rgba(255, 167, 38, 0.1) 2px,
          transparent 2px,
          transparent 4px
        )`
      };
    case 'responding':
      return {
        animation: respondingPulse,
        color: '#00E676',  // Bright green
        scanlineColor: 'rgba(0, 230, 118, 0.15)',
        borderColor: '#00C853',
        gradientStart: '#0A2615',  // Deep forest green
        gradientEnd: 'rgba(10, 38, 21, 0.85)',
        glowColor: 'rgba(0, 230, 118, 0.45)',
        textColor: '#69F0AE',  // Light green
        progressBarColors: 'linear-gradient(90deg, #0A2615, #00E676, #69F0AE)',
        showAnimation: true,
        backgroundOpacity: 0.92,
        backgroundPattern: `repeating-linear-gradient(
          -45deg,
          rgba(0, 230, 118, 0.1) 0px,
          rgba(0, 230, 118, 0.1) 2px,
          transparent 2px,
          transparent 4px
        )`
      };
    case 'idle':
      return {
        animation: 'none',
        color: '#4FC3F7',  // Light blue
        scanlineColor: 'rgba(79, 195, 247, 0.1)',
        borderColor: '#0288D1',
        gradientStart: '#0A1926',  // Deep navy
        gradientEnd: 'rgba(10, 25, 38, 0.85)',
        glowColor: 'rgba(79, 195, 247, 0.3)',
        textColor: '#81D4FA',  // Lighter blue
        progressBarColors: 'linear-gradient(90deg, #0A1926, #4FC3F7, #81D4FA)',
        showAnimation: false,
        backgroundOpacity: 1,
        backgroundPattern: 'none'  // Remove the pattern for idle state
      };
    default:
      return {
        animation: 'none',
        color: '#4FC3F7',  // Light blue
        scanlineColor: 'rgba(79, 195, 247, 0.1)',
        borderColor: '#0288D1',
        gradientStart: '#0A1926',  // Deep navy
        gradientEnd: 'rgba(10, 25, 38, 0.85)',
        glowColor: 'rgba(79, 195, 247, 0.3)',
        textColor: '#81D4FA',  // Lighter blue
        progressBarColors: 'linear-gradient(90deg, #0A1926, #4FC3F7, #81D4FA)',
        showAnimation: false,
        backgroundOpacity: 0.95,
        backgroundPattern: `repeating-linear-gradient(
          90deg,
          rgba(79, 195, 247, 0.05) 0px,
          rgba(79, 195, 247, 0.05) 1px,
          transparent 1px,
          transparent 4px
        )`
      };
  }
};

interface AgentCardProps {
  agent: Agent;
}

export const AgentCard: React.FC<AgentCardProps> = ({ agent }) => {
  const { sendMessage } = useAgentStore();
  const [isHovered, setIsHovered] = useState(false);
  const [randomDelay, setRandomDelay] = useState(0);
  
  // Calculate statusSettings directly from agent.status instead of using state
  const statusSettings = getStatusAnimation(agent.status);
  
  useEffect(() => {
    // Set a random delay for animations to create a more organic feel
    setRandomDelay(Math.random() * 5);
  }, []);
  
  // Remove the useEffect for statusSettings since we're calculating it directly
  
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
  
  return (
    <Card 
      sx={{ 
        height: '100%', 
        display: 'flex', 
        flexDirection: 'column',
        position: 'relative',
        backgroundColor: agent.status === 'idle' ? statusSettings.gradientStart : `rgba(0, 0, 0, ${statusSettings.backgroundOpacity})`,
        backdropFilter: 'blur(5px)',
        border: `1px solid ${statusSettings.borderColor}`,
        boxShadow: isHovered 
          ? `0 0 20px ${statusSettings.glowColor}, inset 0 0 15px ${statusSettings.glowColor}` 
          : `0 0 15px ${statusSettings.glowColor}, inset 0 0 10px ${statusSettings.glowColor}`,
        transition: 'all 0.3s ease',
        overflow: 'hidden',
        transform: isHovered ? 'translateY(-2px)' : 'none',
        '&::before': statusSettings.backgroundPattern === 'none' ? {} : {
          content: '""',
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          background: statusSettings.backgroundPattern,
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
          background: `linear-gradient(180deg, 
            transparent 0%, 
            ${statusSettings.scanlineColor} 50%, 
            transparent 100%
          )`,
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
        {/* Agent Name at the top */}
        <Typography 
          variant="h6" 
          component="h2"
          sx={{ 
            fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
            color: statusSettings.textColor,
            textShadow: isHovered ? `0 0 10px ${statusSettings.color}` : `0 0 5px ${statusSettings.color}`,
            letterSpacing: '0.05em',
            animation: `${flicker} ${5 + randomDelay}s infinite`,
            display: 'flex',
            alignItems: 'center',
            gap: '4px', // Reduced gap
            fontSize: '1rem', // Slightly larger for emphasis
            lineHeight: 1.2, // Tighter line height
            mb: 1, // Add margin below name
            textAlign: 'center',
            width: '100%',
            justifyContent: 'center'
          }}
        >
          <CodeIcon sx={{ fontSize: '0.9em', opacity: 0.8 }} />
          {agent.name}
        </Typography>

        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 0.5 }}>
          {/* Model and Provider info */}
          <Typography 
            variant="caption" 
            color="text.secondary" 
            sx={{ 
              fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
              color: `rgba(${statusSettings.color.replace(/[^\d,]/g, '')}, 0.7)`,
              textShadow: `0 0 3px rgba(${statusSettings.color.replace(/[^\d,]/g, '')}, 0.5)`,
              letterSpacing: '0.05em',
              fontSize: '0.65rem', // Smaller font
              lineHeight: 1.1 // Tighter line height
            }}
          >
            {agent.model && `${agent.model}`}{agent.model && agent.provider && ' • '}{agent.provider && `${agent.provider}`}
          </Typography>
          
          {/* Status Chip */}
          <Chip 
            label={agent.status} 
            color={
              agent.status === 'idle' ? 'primary' :
              agent.status === 'responding' ? 'success' : 
              agent.status === 'thinking' ? 'warning' : 'default'
            }
            size="small"
            sx={{
              fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
              letterSpacing: '0.05em',
              animation: agent.status !== 'idle' ? `${statusSettings.animation} 2s infinite` : 'none',
              textShadow: `0 0 5px ${statusSettings.color}`,
              border: `1px solid ${statusSettings.borderColor}`,
              background: `linear-gradient(to right, ${statusSettings.gradientStart}, ${statusSettings.gradientEnd})`,
              boxShadow: `0 0 5px ${statusSettings.color}`,
              height: '20px', // Smaller height
              '& .MuiChip-label': {
                padding: '0 6px', // Reduced padding
                fontSize: '0.65rem' // Smaller font
              }
            }}
          />
        </Box>
        
        <Box sx={{ mt: 1 }}>
          <Typography 
            variant="caption" 
            color="text.secondary"
            sx={{ 
              fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
              color: `rgba(${statusSettings.color.replace(/[^\d,]/g, '')}, 0.7)`,
              textShadow: `0 0 2px rgba(${statusSettings.color.replace(/[^\d,]/g, '')}, 0.3)`,
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
                  border: `1px solid ${statusSettings.borderColor}`,
                  background: 'transparent',
                  color: statusSettings.textColor,
                  textShadow: `0 0 3px rgba(${statusSettings.color.replace(/[^\d,]/g, '')}, 0.5)`,
                  transition: 'all 0.3s ease',
                  height: '18px', // Smaller height
                  '& .MuiChip-label': {
                    padding: '0 4px', // Reduced padding
                  },
                  '&:hover': {
                    boxShadow: `0 0 5px ${statusSettings.color}`,
                    borderColor: statusSettings.color,
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
            color: `rgba(${statusSettings.color.replace(/[^\d,]/g, '')}, 0.7)`,
            textShadow: `0 0 2px rgba(${statusSettings.color.replace(/[^\d,]/g, '')}, 0.3)`,
            letterSpacing: '0.05em',
            mt: 0.5, // Reduced margin
            fontSize: '0.65rem', // Smaller font
            lineHeight: 1.1 // Tighter line height
          }}
        >
          Type: {agent.type}
        </Typography>
        
        {/* Add a subtle progress bar for visual effect when not idle */}
        {agent.status !== 'idle' && (
          <Box sx={{ mt: 1, mb: 0 }}>
            <LinearProgress 
              variant="indeterminate" 
              sx={{
                height: '2px',
                borderRadius: '1px',
                backgroundColor: statusSettings.gradientStart,
                '.MuiLinearProgress-bar': {
                  background: statusSettings.progressBarColors,
                  boxShadow: `0 0 5px ${statusSettings.color}`,
                }
              }}
            />
          </Box>
        )}
      </CardContent>
      
      <CardActions sx={{ 
        justifyContent: 'flex-end', 
        borderTop: `1px solid ${statusSettings.borderColor}`,
        background: `rgba(${statusSettings.gradientStart.replace(/[^\d,]/g, '')}, 0.3)`,
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
            color: statusSettings.textColor,
            transition: 'all 0.3s ease',
            padding: '4px', // Smaller padding
            '&:hover': {
              backgroundColor: `rgba(${statusSettings.color.replace(/[^\d,]/g, '')}, 0.1)`,
              transform: 'scale(1.1)',
              boxShadow: `0 0 10px ${statusSettings.color}`,
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
            color: statusSettings.textColor,
            transition: 'all 0.3s ease',
            padding: '4px', // Smaller padding
            '&:hover': {
              backgroundColor: `rgba(${statusSettings.color.replace(/[^\d,]/g, '')}, 0.1)`,
              transform: 'scale(1.1)',
              boxShadow: `0 0 10px ${statusSettings.color}`,
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
            color: statusSettings.textColor,
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