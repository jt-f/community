import { useState, useEffect } from 'react';
import { AgentStatus, AgentStatusUpdateMessage, MessageType } from '../types/message';

interface AgentStatusProps {
  wsRef: React.MutableRefObject<WebSocket | null>;
}

export function AgentStatusPanel({ wsRef }: AgentStatusProps) {
  const [agents, setAgents] = useState<AgentStatus[]>([]);

  useEffect(() => {
    // Handle agent status updates
    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        
        // Only process agent status update messages
        if (data.message_type === MessageType.AGENT_STATUS_UPDATE) {
          const statusUpdate = data as AgentStatusUpdateMessage;
          setAgents(statusUpdate.agents);
        }
      } catch (error) {
        console.error('Error processing agent status update:', error);
      }
    };

    // Add the message handler if the websocket is available
    if (wsRef.current) {
      wsRef.current.addEventListener('message', handleMessage);
    }

    // Clean up the event listener when the component unmounts
    return () => {
      if (wsRef.current) {
        wsRef.current.removeEventListener('message', handleMessage);
      }
    };
  }, [wsRef]);

  return (
    <div className="agent-status-panel">
      <div className="panel-header">
        <h3>Agent Status</h3>
        <span className="agent-count">{agents.length} agents</span>
      </div>
      
      <div className="agents-list">
        {agents.length === 0 ? (
          <div className="no-agents">No agents connected</div>
        ) : (
          agents.map(agent => (
            <div key={agent.agent_id} className="agent-item">
              <div className="agent-info">
                <span className="agent-name">{agent.agent_name}</span>
                <span className="agent-id">ID: {agent.agent_id.substring(0, 8)}</span>
              </div>
              <div className="agent-status">
                <div className={`status-indicator ${agent.is_online ? 'online' : 'offline'}`}></div>
                <span className="status-text">{agent.is_online ? 'Online' : 'Offline'}</span>
                <span className="last-seen">Last seen: {agent.last_seen}</span>
              </div>
            </div>
          ))
        )}
      </div>
      
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
         
         .agents-list {
           padding: 8px;
           overflow-y: auto;
           flex-grow: 1;
         }
         
         .no-agents {
           text-align: center;
           color: var(--color-text-muted);
           padding: 20px 0;
           font-style: italic;
         }
         
         .agent-item {
           padding: 10px;
           border-bottom: 1px solid var(--color-border);
           display: flex;
           flex-direction: column;
           gap: 6px;
         }
         
         .agent-item:last-child {
           border-bottom: none;
         }
         
         .agent-info {
           display: flex;
           justify-content: space-between;
           align-items: center;
         }
         
         .agent-name {
           font-weight: 500;
           font-size: 14px;
         }
         
         .agent-id {
           font-size: 12px;
           color: var(--color-text-muted);
         }
         
         .agent-status {
           display: flex;
           align-items: center;
           font-size: 12px;
           gap: 6px;
         }
         
         .status-indicator {
           width: 8px;
           height: 8px;
           border-radius: 50%;
         }
         
         .status-indicator.online {
           background-color: #4caf50;
           box-shadow: 0 0 4px #4caf50;
         }
         
         .status-indicator.offline {
           background-color: #f44336;
         }
         
         .status-text {
           font-weight: 500;
         }
         
         .last-seen {
           margin-left: auto;
           color: var(--color-text-muted);
         }
        `}
      </style>
    </div>
  );
} 