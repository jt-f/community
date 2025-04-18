import React from 'react';
import { AgentList } from './AgentList';
import { useAgentStore } from '../store/agentStore';

interface AgentStatusPanelProps {
  wsRef: React.MutableRefObject<WebSocket | null>;
}

export function AgentStatusPanel({ wsRef }: AgentStatusPanelProps) {
  // Use Zustand for agent state
  const { agents } = useAgentStore();

  return (
    <div className="agent-status-panel">
      <div className="panel-header">
        <h3>Agent Status</h3>
        <span className="agent-count">{agents.length} agents</span>
      </div>
      <AgentList agents={agents} showId emptyText="No agents connected" />
      <style>
        {`
         .agent-status-panel {
           width: 300px;
           border: 1px solid var(--color-border-strong);
           border-radius: 4px;
           background-color: var(--color-surface);
           margin-left: 20px;
           display: flex;
           flex-direction: column;
           box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
         }
         
         .panel-header {
           display: flex;
           justify-content: space-between;
           align-items: center;
           padding: 12px 16px;
           background-color: var(--color-surface-raised);
           border-bottom: 1px solid var(--color-border);
         }
         
         .panel-header h3 {
           margin: 0;
           font-size: 16px;
           font-weight: 600;
         }
         
         .agent-count {
           font-size: 12px;
           color: var(--color-text-muted);
           background-color: var(--color-surface-sunken);
           padding: 2px 8px;
           border-radius: 12px;
         }
        `}
      </style>
    </div>
  );
}