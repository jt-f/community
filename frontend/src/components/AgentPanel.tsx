import { useState, useEffect } from 'react';
import { AgentStatusUpdateMessage, MessageType } from '../types/message';
import { useAgentStore } from '../store/agentStore';

interface AgentPanelProps {
  wsRef: React.MutableRefObject<WebSocket | null>;
}

export function AgentPanel({ wsRef }: AgentPanelProps) {
  const { agents, updateAgents, getOnlineAgents, getOfflineAgents } = useAgentStore();
  const [selectedFilter, setSelectedFilter] = useState<'all' | 'online' | 'offline'>('all');

  useEffect(() => {
    // Setup websocket message handler for agent status updates
    const handleMessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        console.log('Received WebSocket message:', data);
        
        // Only process agent status update messages
        if (data.message_type === MessageType.AGENT_STATUS_UPDATE) {
          console.log('Processing agent status update:', data);
          const statusUpdate = data as AgentStatusUpdateMessage;
          console.log('Updating agents with:', statusUpdate.agents);
          updateAgents(statusUpdate.agents);
        }
      } catch (error) {
        console.error('Error processing agent status update:', error);
      }
    };

    // Add the message handler if the websocket is available
    if (wsRef.current) {
      console.log('Adding message handler to WebSocket');
      wsRef.current.addEventListener('message', handleMessage);
    } else {
      console.warn('WebSocket not available when setting up message handler');
    }

    // Clean up the event listener when the component unmounts
    return () => {
      if (wsRef.current) {
        console.log('Removing message handler from WebSocket');
        wsRef.current.removeEventListener('message', handleMessage);
      }
    };
  }, [wsRef, updateAgents]);

  // Log current agents state
  useEffect(() => {
    console.log('Current agents state:', agents);
  }, [agents]);

  // Get the agents to display based on selected filter
  const getFilteredAgents = () => {
    switch (selectedFilter) {
      case 'online':
        return getOnlineAgents();
      case 'offline':
        return getOfflineAgents();
      default:
        return agents;
    }
  };

  const filteredAgents = getFilteredAgents();

  return (
    <div className="agent-panel">
      <div className="panel-header">
        <h3>Agents</h3>
        <div className="agent-filters">
          <button 
            className={`filter-btn ${selectedFilter === 'all' ? 'active' : ''}`}
            onClick={() => setSelectedFilter('all')}
          >
            All ({agents.length})
          </button>
          <button 
            className={`filter-btn ${selectedFilter === 'online' ? 'active' : ''}`}
            onClick={() => setSelectedFilter('online')}
          >
            Online ({getOnlineAgents().length})
          </button>
          <button 
            className={`filter-btn ${selectedFilter === 'offline' ? 'active' : ''}`}
            onClick={() => setSelectedFilter('offline')}
          >
            Offline ({getOfflineAgents().length})
          </button>
        </div>
      </div>
      
      <div className="agents-list">
        {filteredAgents.length === 0 ? (
          <div className="no-agents">
            {selectedFilter === 'all' 
              ? 'No agents registered'
              : selectedFilter === 'online'
                ? 'No agents online'
                : 'No agents offline'
            }
          </div>
        ) : (
          filteredAgents.map(agent => (
            <div key={agent.agent_id} className="agent-item">
              <div className="agent-info">
                <div className="agent-name-container">
                  <div className={`status-indicator ${agent.is_online ? 'online' : 'offline'}`}></div>
                  <span className="agent-name">{agent.agent_name}</span>
                </div>
                <span className="agent-id">ID: {agent.agent_id.substring(0, 8)}</span>
              </div>
              <div className="agent-meta">
                <span className="last-seen">Last seen: {agent.last_seen}</span>
                <span className="status-text">{agent.is_online ? 'Online' : 'Offline'}</span>
              </div>
            </div>
          ))
        )}
      </div>
      
      <style>
        {`
        .agent-panel {
          width: 300px;
          border: 1px solid var(--color-border-strong);
          border-radius: 4px;
          background-color: var(--color-surface);
          margin-left: 20px;
          display: flex;
          flex-direction: column;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
          height: calc(100vh - 120px);
        }
        
        .panel-header {
          display: flex;
          flex-direction: column;
          gap: 8px;
          padding: 12px 16px;
          background-color: var(--color-surface-raised);
          border-bottom: 1px solid var(--color-border);
        }
        
        .panel-header h3 {
          margin: 0;
          font-size: 16px;
          font-weight: 600;
        }
        
        .agent-filters {
          display: flex;
          gap: 8px;
        }
        
        .filter-btn {
          background: var(--color-surface);
          border: 1px solid var(--color-border);
          border-radius: 12px;
          padding: 2px 8px;
          font-size: 12px;
          cursor: pointer;
          transition: all 0.2s;
        }
        
        .filter-btn.active {
          background-color: var(--color-primary);
          color: white;
          border-color: var(--color-primary);
        }
        
        .filter-btn:hover:not(.active) {
          border-color: var(--color-primary-muted);
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
          padding: 12px;
          border-radius: 4px;
          margin-bottom: 8px;
          background-color: var(--color-surface-raised);
          transition: all 0.2s;
        }
        
        .agent-item:hover {
          transform: translateY(-2px);
          box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
        }
        
        .agent-info {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
        }
        
        .agent-name-container {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        
        .agent-name {
          font-weight: 500;
          font-size: 14px;
        }
        
        .agent-id {
          font-size: 12px;
          color: var(--color-text-muted);
        }
        
        .agent-meta {
          display: flex;
          justify-content: space-between;
          font-size: 12px;
          color: var(--color-text-muted);
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
          color: var(--color-text-secondary);
        }
        
        .last-seen {
          color: var(--color-text-tertiary);
        }
        `}
      </style>
    </div>
  );
} 