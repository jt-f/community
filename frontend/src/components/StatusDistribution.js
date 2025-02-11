import React from 'react';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Legend,
  Tooltip,
} from 'recharts';
import { Card, CardContent, Typography } from '@mui/material';

const COLORS = {
  active: '#4caf50',
  idle: '#2196f3',
  busy: '#ff9800',
  error: '#f44336',
  default: '#9e9e9e',
};

function StatusDistribution({ agents }) {
  const statusCounts = agents.reduce((acc, agent) => {
    const status = agent.status.toLowerCase();
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, {});

  const data = Object.entries(statusCounts).map(([status, count]) => ({
    name: status.charAt(0).toUpperCase() + status.slice(1),
    value: count,
  }));

  const renderCustomizedLabel = ({
    cx,
    cy,
    midAngle,
    innerRadius,
    outerRadius,
    percent,
  }) => {
    const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
    const x = cx + radius * Math.cos(-midAngle * (Math.PI / 180));
    const y = cy + radius * Math.sin(-midAngle * (Math.PI / 180));

    return percent > 0.05 ? (
      <text
        x={x}
        y={y}
        fill="white"
        textAnchor="middle"
        dominantBaseline="central"
      >
        {`${(percent * 100).toFixed(0)}%`}
      </text>
    ) : null;
  };

  return (
    <Card sx={{ height: '100%', minHeight: 300 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Agent Status Distribution
        </Typography>
        <ResponsiveContainer width="100%" height={250}>
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              labelLine={false}
              label={renderCustomizedLabel}
              outerRadius={80}
              fill="#8884d8"
              dataKey="value"
              animationDuration={1000}
            >
              {data.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={COLORS[entry.name.toLowerCase()] || COLORS.default}
                />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                background: 'rgba(255, 255, 255, 0.9)',
                border: 'none',
                borderRadius: 4,
                boxShadow: '0 2px 5px rgba(0,0,0,0.2)',
              }}
            />
            <Legend verticalAlign="bottom" height={36} />
          </PieChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

export default StatusDistribution; 