import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { Card, CardContent, Typography } from '@mui/material';

function QueueChart({ agents }) {
  const data = agents.map(agent => ({
    name: agent.name,
    queueSize: agent.queue_size,
  }));

  return (
    <Card sx={{ height: '100%', minHeight: 300 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Message Queue Sizes
        </Typography>
        <ResponsiveContainer width="100%" height={250}>
          <BarChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 12 }}
              interval={0}
              angle={-45}
              textAnchor="end"
            />
            <YAxis />
            <Tooltip
              contentStyle={{
                background: 'rgba(255, 255, 255, 0.9)',
                border: 'none',
                borderRadius: 4,
                boxShadow: '0 2px 5px rgba(0,0,0,0.2)',
              }}
            />
            <Bar
              dataKey="queueSize"
              fill="#90caf9"
              radius={[4, 4, 0, 0]}
              animationDuration={1000}
            />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

export default QueueChart; 