import React from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  List,
  ListItem,
  ListItemText,
  Divider,
  Badge,
  Chip,
} from '@mui/material';
import { Queue as QueueIcon } from '@mui/icons-material';

function AgentQueues({ agents }) {
  return (
    <Card sx={{ height: '100%', minHeight: 300 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <QueueIcon />
          Agent Message Queues
        </Typography>
        <List>
          {Object.values(agents).map((agent, index) => (
            <React.Fragment key={agent.id}>
              {index > 0 && <Divider />}
              <ListItem
                sx={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'flex-start',
                  py: 2,
                }}
              >
                <Box sx={{ width: '100%', display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                  <Typography variant="subtitle1" component="div">
                    {agent.name}
                  </Typography>
                  <Badge
                    badgeContent={agent.queue_size}
                    color={agent.queue_size > 5 ? 'error' : 'primary'}
                    max={99}
                  >
                    <Chip
                      label="Queue"
                      size="small"
                      variant="outlined"
                      color={agent.queue_size > 5 ? 'error' : 'primary'}
                    />
                  </Badge>
                </Box>
                <Box sx={{ width: '100%' }}>
                  <Typography variant="body2" color="text.secondary">
                    Status: {agent.status}
                  </Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 1 }}>
                    {agent.capabilities.map((cap, idx) => (
                      <Chip
                        key={idx}
                        label={cap}
                        size="small"
                        variant="outlined"
                        sx={{ fontSize: '0.7rem' }}
                      />
                    ))}
                  </Box>
                </Box>
              </ListItem>
            </React.Fragment>
          ))}
          {Object.keys(agents).length === 0 && (
            <ListItem>
              <ListItemText
                primary="No agents registered"
                secondary="Waiting for agents to connect..."
                sx={{ textAlign: 'center', color: 'text.secondary' }}
              />
            </ListItem>
          )}
        </List>
      </CardContent>
    </Card>
  );
}

export default AgentQueues; 