import React from 'react';
import {
  AppBar,
  Toolbar,
  Typography,
  Box,
  Chip,
  IconButton,
  Tooltip,
} from '@mui/material';
import {
  CloudDone as ConnectedIcon,
  CloudOff as DisconnectedIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { useAgentStore } from '../store/agentStore';

function Header() {
  const { connected, error, agents, connect, getTotalQueueSize } = useAgentStore();

  const totalAgents = Object.keys(agents).length;
  const totalQueueSize = getTotalQueueSize();

  return (
    <AppBar position="static" elevation={0} sx={{ background: 'transparent', backdropFilter: 'blur(10px)' }}>
      <Toolbar>
        <Typography variant="h6" component="div" sx={{ flexGrow: 0, mr: 3 }}>
          Agent Monitor
        </Typography>

        <Chip
          icon={connected ? <ConnectedIcon /> : <DisconnectedIcon />}
          label={connected ? 'Connected' : 'Disconnected'}
          color={connected ? 'success' : 'error'}
          size="small"
          sx={{ mr: 2 }}
        />

        <Box sx={{ flexGrow: 1, display: 'flex', gap: 2 }}>
          <Chip
            label={`Agents: ${totalAgents}`}
            color="primary"
            variant="outlined"
            size="small"
          />
          <Chip
            label={`Queue Size: ${totalQueueSize}`}
            color="secondary"
            variant="outlined"
            size="small"
          />
        </Box>

        {!connected && (
          <Tooltip title="Reconnect">
            <IconButton color="primary" onClick={connect} size="small">
              <RefreshIcon />
            </IconButton>
          </Tooltip>
        )}
      </Toolbar>
    </AppBar>
  );
}

export default Header; 