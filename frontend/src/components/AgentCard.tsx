import React, { useEffect, useState, ErrorInfo } from 'react';
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
  keyframes,
  Collapse
} from '@mui/material';
import {
  Memory as MemoryIcon,
  Queue as QueueIcon,
  Update as UpdateIcon,
  Message as MessageIcon,
  Delete as DeleteIcon,
  Refresh as RefreshIcon,
  Code as CodeIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon
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

// Define a vibration animation for "thinking" state
const vibrate = keyframes`
  0% { transform: translate(0); }
  20% { transform: translate(-1px, 1px); }
  40% { transform: translate(1px, -1px); }
  60% { transform: translate(-1px, -1px); }
  80% { transform: translate(1px, 1px); }
  100% { transform: translate(0); }
`;

// Helper function to safely parse hex color to RGB
const hexToRgb = (hex: string) => {
  // Default fallback color components 
  const defaultR = 79;
  const defaultG = 195;
  const defaultB = 247;
  
  return {
    r: getSafe(() => parseInt(hex.slice(1, 3), 16), defaultR),
    g: getSafe(() => parseInt(hex.slice(3, 5), 16), defaultG),
    b: getSafe(() => parseInt(hex.slice(5, 7), 16), defaultB)
  };
};

// Function to get animation settings based on status
const getStatusAnimation = (status: string) => {
  try {
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
          backgroundOpacity: 1,
          backgroundPattern: 'none'  // Remove the pattern for idle state
        };
    }
  } catch (error) {
    console.error("Error in getStatusAnimation:", error);
    // Return fallback default values
    return {
      animation: 'none',
      color: '#4FC3F7',
      scanlineColor: 'rgba(79, 195, 247, 0.1)',
      borderColor: '#0288D1',
      gradientStart: '#0A1926',
      gradientEnd: 'rgba(10, 25, 38, 0.85)',
      glowColor: 'rgba(79, 195, 247, 0.3)',
      textColor: '#81D4FA',
      progressBarColors: 'linear-gradient(90deg, #0A1926, #4FC3F7, #81D4FA)',
      showAnimation: false,
      backgroundOpacity: 1,
      backgroundPattern: 'none'
    };
  }
};

interface AgentCardProps {
  agent: Agent;
}

// Error boundary component to catch rendering errors
class AgentCardErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; errorMessage: string }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { 
      hasError: false,
      errorMessage: ''
    };
  }

  static getDerivedStateFromError(error: any) {
    return { 
      hasError: true,
      errorMessage: error?.message || 'Unknown error'
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Error in AgentCard:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      // Fallback UI
      return (
        <Card sx={{ 
          height: '100%', 
          display: 'flex', 
          flexDirection: 'column',
          p: 2,
          backgroundColor: 'rgba(10, 10, 10, 0.85)',
          border: '1px solid #880E0E',
          boxShadow: '0 0 15px rgba(255, 0, 0, 0.3)',
        }}>
          <Typography color="error" variant="body2">
            Error rendering agent card: {this.state.errorMessage}
          </Typography>
        </Card>
      );
    }

    return this.props.children;
  }
}

// Wrap the original AgentCard with the error boundary
export const AgentCard: React.FC<AgentCardProps> = (props) => {
  return (
    <AgentCardErrorBoundary>
      <AgentCardContent {...props} />
    </AgentCardErrorBoundary>
  );
};

// Add a safe accessor function for nested object properties
const getSafe = <T extends any>(fn: () => T, defaultValue: T): T => {
  try {
    const value = fn();
    // Check for React's invalid children types
    if (value === null || value === undefined) {
      return defaultValue;
    }
    // Handle potential object with error key that can't be rendered directly
    if (typeof value === 'object' && 'error' in value) {
      console.error('Error object detected in props:', value);
      return defaultValue;
    }
    return value;
  } catch (e) {
    console.error('Error accessing property:', e);
    return defaultValue;
  }
};

// The actual card content component
const AgentCardContent: React.FC<AgentCardProps> = ({ agent }) => {
  const { sendMessage } = useAgentStore();
  const [isHovered, setIsHovered] = useState(false);
  const [randomDelay, setRandomDelay] = useState(0);
  const [isCollapsed, setIsCollapsed] = useState(true);
  
  // Ensure agent has all required properties with defaults
  const safeAgent = {
    id: getSafe(() => agent?.id, 'unknown'),
    name: getSafe(() => agent?.name, 'Unknown Agent'),
    type: getSafe(() => agent?.type, 'unknown'),
    status: getSafe(() => agent?.status, 'idle'),
    capabilities: getSafe(() => Array.isArray(agent?.capabilities) ? agent.capabilities : [], []),
    model: getSafe(() => agent?.model, 'Default'),
    provider: getSafe(() => agent?.provider, 'Default')
  };
  
  // Calculate statusSettings directly from agent.status instead of using state
  const statusSettings = getStatusAnimation(safeAgent.status);
  
  useEffect(() => {
    // Set a random delay for animations to create a more organic feel
    setRandomDelay(Math.random() * 5);
  }, []);
  
  // Remove the useEffect for statusSettings since we're calculating it directly
  
  const handleMessageClick = () => {
    // Implement message sending logic
    console.log(`Send message to ${safeAgent.name}`);
  };
  
  const handleDeleteClick = () => {
    // Implement agent deletion logic
    console.log(`Delete agent ${safeAgent.name}`);
  };
  
  const handleRefreshClick = () => {
    // Implement agent refresh logic
    console.log(`Refresh agent ${safeAgent.name}`);
  };
  
  const toggleCollapse = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsCollapsed(!isCollapsed);
  };
  
  return (
    <Card 
      sx={{ 
        height: '100%', 
        display: 'flex', 
        flexDirection: 'column',
        position: 'relative',
        backgroundColor: safeAgent.status === 'idle' ? statusSettings.gradientStart : `rgba(0, 0, 0, ${statusSettings.backgroundOpacity})`,
        backdropFilter: 'blur(5px)',
        border: `1px solid ${statusSettings.borderColor}`,
        boxShadow: isHovered 
          ? `0 0 20px ${statusSettings.glowColor}, inset 0 0 15px ${statusSettings.glowColor}` 
          : `0 0 15px ${statusSettings.glowColor}, inset 0 0 10px ${statusSettings.glowColor}`,
        transition: 'all 0.3s ease',
        overflow: 'hidden',
        animation: safeAgent.status === 'thinking' ? `${vibrate} 0.3s linear infinite` : 'none',
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
        p: isCollapsed ? '5px 8px' : 1, // More compact when collapsed
        '&:last-child': { pb: isCollapsed ? 5 : 8 } // Override default padding
      }}>
        {/* Agent Name and collapse button at the top */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: isCollapsed ? 0.5 : 0.5 }}>
          <Box sx={{ width: '100%' }}>
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
                gap: '2px',
                fontSize: '0.9rem',
                lineHeight: 1.1,
                mb: 0.5,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                maxWidth: '100%'
              }}
            >
              <MemoryIcon 
                sx={{ 
                  fontSize: '0.85rem', 
                  mr: 0.5,
                  animation: statusSettings.showAnimation ? `${pulse} ${3 + randomDelay}s infinite ease-in-out` : 'none',
                }} 
              />
              {safeAgent.name}
            </Typography>
            
            {isCollapsed && (
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <Chip 
                  label={safeAgent.status.toUpperCase()}
                  size="small"
                  sx={{ 
                    fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                    backgroundColor: `rgba(${hexToRgb(statusSettings.color).r}, ${hexToRgb(statusSettings.color).g}, ${hexToRgb(statusSettings.color).b}, 0.15)`,
                    color: statusSettings.color,
                    border: `1px solid ${statusSettings.color}`,
                    fontSize: '0.55rem',
                    height: '16px',
                    mr: 0.5,
                    maxWidth: '60px',
                    '& .MuiChip-label': {
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      padding: '0 4px'
                    }
                  }} 
                />
                <Chip 
                  label={safeAgent.type.toUpperCase()}
                  size="small"
                  sx={{ 
                    fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                    backgroundColor: 'rgba(10, 10, 10, 0.7)',
                    color: '#B3E5FC',
                    border: '1px solid #0288D1',
                    fontSize: '0.55rem',
                    height: '16px',
                    maxWidth: '60px',
                    '& .MuiChip-label': {
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      padding: '0 4px'
                    }
                  }} 
                />
              </Box>
            )}
          </Box>
          
          <IconButton 
            size="small" 
            onClick={toggleCollapse}
            sx={{ 
              p: 0.25,
              ml: 0.5,
              color: statusSettings.color,
              '&:hover': { 
                backgroundColor: `rgba(${hexToRgb(statusSettings.color).r}, ${hexToRgb(statusSettings.color).g}, ${hexToRgb(statusSettings.color).b}, 0.1)` 
              }
            }}
          >
            {isCollapsed ? <ExpandMoreIcon fontSize="small" /> : <ExpandLessIcon fontSize="small" />}
          </IconButton>
        </Box>
        
        {/* Status chip - only show when not collapsed */}
        {!isCollapsed && (
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
            <Chip 
              label={safeAgent.status.toUpperCase()}
              size="small"
              sx={{ 
                fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                backgroundColor: `rgba(${hexToRgb(statusSettings.color).r}, ${hexToRgb(statusSettings.color).g}, ${hexToRgb(statusSettings.color).b}, 0.15)`,
                color: statusSettings.color,
                border: `1px solid ${statusSettings.color}`,
                fontSize: '0.6rem',
                height: '20px',
                mr: 0.5,
                maxWidth: '70px',
                '& .MuiChip-label': {
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  padding: '0 6px'
                }
              }} 
            />
            <Chip 
              label={safeAgent.type.toUpperCase()}
              size="small"
              sx={{ 
                fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                backgroundColor: 'rgba(10, 10, 10, 0.7)',
                color: '#B3E5FC',
                border: '1px solid #0288D1',
                fontSize: '0.6rem',
                height: '20px',
                maxWidth: '70px',
                '& .MuiChip-label': {
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  padding: '0 6px'
                }
              }} 
            />
          </Box>
        )}
        
        {/* Collapsible content */}
        <Collapse in={!isCollapsed} timeout="auto" unmountOnExit>
          <Box sx={{ mt: 1 }}>
            {/* Type row with model info */}
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
              <Typography 
                variant="caption" 
                sx={{ 
                  fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                  color: '#B3E5FC',
                  fontSize: '0.65rem',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  maxWidth: '100%',
                  display: 'block'
                }}
              >
                <strong>Model:</strong> {safeAgent.model}
              </Typography>
            </Box>
            
            {/* Provider info */}
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
              <Typography 
                variant="caption" 
                sx={{ 
                  fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                  color: '#B3E5FC',
                  fontSize: '0.65rem',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  maxWidth: '100%',
                  display: 'block'
                }}
              >
                <strong>Provider:</strong> {safeAgent.provider}
              </Typography>
            </Box>
            
            {/* Capabilities list */}
            <Typography 
              variant="caption" 
              sx={{ 
                display: 'block',
                fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                color: '#B3E5FC',
                fontSize: '0.65rem',
                mb: 0.5
              }}
            >
              <strong>Capabilities:</strong>
            </Typography>
            
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mb: 1 }}>
              {safeAgent.capabilities.map((capability, index) => {
                // Ensure capability is a string
                const capabilityStr = typeof capability === 'string' 
                  ? capability 
                  : typeof capability === 'object' && capability !== null
                    ? JSON.stringify(capability).slice(0, 20) 
                    : String(capability || '');
                    
                return (
                  <Chip 
                    key={index}
                    label={capabilityStr}
                    size="small"
                    sx={{ 
                      fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
                      backgroundColor: 'rgba(0, 0, 0, 0.3)',
                      color: '#B3E5FC',
                      border: '1px solid #0288D1',
                      fontSize: '0.6rem',
                      height: '16px',
                      py: 0,
                      px: 0.25,
                      maxWidth: '80px',
                      '& .MuiChip-label': {
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        padding: '0 4px'
                      }
                    }} 
                  />
                );
              })}
            </Box>
            
            {/* Button row */}
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
              <Tooltip title="Message Agent">
                <IconButton 
                  size="small" 
                  onClick={handleMessageClick}
                  sx={{ 
                    color: '#4FC3F7',
                    p: 0.5,
                    '&:hover': { color: '#81D4FA', backgroundColor: 'rgba(79, 195, 247, 0.1)' } 
                  }}
                >
                  <MessageIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              
              <Tooltip title="Refresh Agent">
                <IconButton 
                  size="small" 
                  onClick={handleRefreshClick}
                  sx={{ 
                    color: '#4FC3F7',
                    p: 0.5,
                    '&:hover': { color: '#81D4FA', backgroundColor: 'rgba(79, 195, 247, 0.1)' } 
                  }}
                >
                  <RefreshIcon fontSize="small" />
                </IconButton>
              </Tooltip>
              
              <Tooltip title="Delete Agent">
                <IconButton 
                  size="small" 
                  onClick={handleDeleteClick}
                  sx={{ 
                    color: '#EF5350',
                    p: 0.5,
                    '&:hover': { color: '#E57373', backgroundColor: 'rgba(239, 83, 80, 0.1)' } 
                  }}
                >
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Box>
          </Box>
        </Collapse>
      </CardContent>
    </Card>
  );
}; 