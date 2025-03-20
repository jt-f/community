import React, { useState, useEffect } from 'react';
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

export const AgentDashboard: React.FC = () => {
  const { agents } = useAgentStore();
  const [showCreationForm, setShowCreationForm] = useState(false);
  const [randomDelay, setRandomDelay] = useState(0);
  
  useEffect(() => {
    // Set a random delay for animations to create a more organic feel
    setRandomDelay(Math.random() * 5);
  }, []);
  
  return (
    <Box 
      sx={{ 
        p: 3,
        position: 'relative',
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
      <Box 
        sx={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center', 
          mb: 3,
          position: 'relative',
          zIndex: 1,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <MemoryIcon 
            sx={{ 
              color: '#00FF41', 
              fontSize: '2rem',
              animation: `${pulse} ${3 + randomDelay}s infinite ease-in-out`,
            }} 
          />
          <Typography 
            variant="h5"
            sx={{ 
              color: '#00FF41',
              fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
              letterSpacing: '0.05em',
              textShadow: '0 0 10px rgba(0, 255, 65, 0.7)',
              animation: `${flicker} ${7 + randomDelay}s infinite`,
              textTransform: 'uppercase',
              position: 'relative',
              fontSize: '1.5rem',
              '&::after': {
                content: '""',
                position: 'absolute',
                bottom: -5,
                left: 0,
                width: '100%',
                height: '1px',
                background: 'linear-gradient(90deg, transparent, rgba(0, 255, 65, 0.5), transparent)',
              }
            }}
          >
            Neural Agent Network
          </Typography>
        </Box>
        <Button 
          variant="contained" 
          startIcon={showCreationForm ? <ExpandLessIcon /> : <AddIcon />}
          onClick={() => setShowCreationForm(!showCreationForm)}
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
        <Grid container spacing={3}>
          {Object.values(agents).map((agent) => (
            <Grid item xs={12} sm={6} md={4} key={agent.id}>
              <AgentCard agent={agent} />
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