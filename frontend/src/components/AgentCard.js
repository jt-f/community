import React from 'react';
import {
  Card,
  CardContent,
  Typography,
  Chip,
  Box,
  LinearProgress,
  Tooltip,
} from '@mui/material';
import {
  Memory as MemoryIcon,
  Queue as QueueIcon,
  Update as UpdateIcon,
} from '@mui/icons-material';

function AgentCard({ agent }) {
  const getStatusColor = (status) => {
    switch (status.toLowerCase()) {
      case 'active':
        return 'success';
      case 'idle':
        return 'info';
      case 'busy':
        return 'warning';
      case 'error':
        return 'error';
      default:
        return 'default';
    }
  };

  const formatTimestamp = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
  };

  return (
    <Card
      sx={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        overflow: 'visible',
        '&:hover': {
          transform: 'translateY(-4px)',
          transition: 'transform 0.2s ease-in-out',
        },
      }}
    >
      <CardContent>
        <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
          <MemoryIcon color="primary" />
          <Typography variant="h6" component="div">
            {agent.name}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ mt: -0.5 }}>
            ID: {agent.id}
          </Typography>
        </Box>

        <Chip
          label={agent.status}
          color={getStatusColor(agent.status)}
          size="small"
          sx={{ mb: 2 }}
        />

        <Box sx={{ mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <QueueIcon fontSize="small" sx={{ mr: 1 }} />
            <Typography variant="body2" color="text.secondary">
              Queue Size
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={Math.min((agent.queue_size / 10) * 100, 100)}
            sx={{ height: 8, borderRadius: 4 }}
          />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
            {agent.queue_size} messages
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <UpdateIcon fontSize="small" />
          <Tooltip title={agent.last_activity}>
            <Typography variant="caption" color="text.secondary">
              Last Active: {formatTimestamp(agent.last_activity)}
            </Typography>
          </Tooltip>
        </Box>

        <Box sx={{ mt: 2 }}>
          <Typography variant="caption" color="text.secondary">
            Capabilities:
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
            {agent.capabilities.map((cap, index) => (
              <Chip
                key={index}
                label={cap}
                size="small"
                variant="outlined"
                sx={{ fontSize: '0.7rem' }}
              />
            ))}
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

export default AgentCard; 