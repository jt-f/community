import { useState, useEffect, useContext } from 'react';
import { MessageType } from '../types/message';
import { useAgentStore } from '../store/agentStore';
import { WebSocketContext } from './ChatUI';

interface AgentPanelProps {
  wsRef: React.MutableRefObject<WebSocket | null>;
  isConnected: boolean;
}

export function AgentPanel({ wsRef, isConnected }: AgentPanelProps) {
  const { agents, updateAgents, getOnlineAgents, getOfflineAgents } = useAgentStore();
  const [selectedFilter, setSelectedFilter] = useState<'all' | 'online' | 'offline'>('all');
  const { lastMessage } = useContext(WebSocketContext);

  // Process messages from WebSocketContext
  useEffect(() => {
    if (lastMessage && lastMessage.message_type === MessageType.AGENT_STATUS_UPDATE) {
      // Only log full updates or when debugging is needed
      if (lastMessage.is_full_update) {
        console.log('AgentPanel: Received full agent status update');
      }
      updateAgents(lastMessage.agents, lastMessage.is_full_update);
    }
  }, [lastMessage, updateAgents]);

  // Get the agents to display based on selected filter
  const getFilteredAgents = () => {
    return selectedFilter === 'online'
      ? getOnlineAgents()
      : selectedFilter === 'offline'
        ? getOfflineAgents()
        : agents;
  };

  const filteredAgents = getFilteredAgents();

  return (
    <div className="agent-panel">
      <div className="panel-header">
        <h3>Agents</h3>
        <div className="connection-status">
          <div className={`status-indicator ${isConnected ? 'online' : 'offline'}`}></div>
          <span className="status-text">{isConnected ? 'Connected' : 'Disconnected'}</span>
        </div>
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
        {!isConnected ? (
          <div className="no-agents">Connecting to server...</div>
        ) : filteredAgents.length === 0 ? (
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
                  <span className="agent-name" title={agent.agent_id}>{agent.agent_name}</span>
                </div>
                {/* Optionally hide or keep the explicit ID display */}
                {/* <span className="agent-id">ID: {agent.agent_id.substring(0, 8)}</span> */}
              </div>
              <div className="agent-meta">
                <span className="last-seen">Last seen: {agent.last_seen ? new Date(agent.last_seen).toLocaleString() : 'Never'}</span>
                <span className="status-text">{agent.is_online ? 'Online' : 'Offline'}</span>
              </div>
            </div>
          ))
        )}
      </div>

      <style>
        {`
        .agent-panel {
          flex: 0 0 38.2%; /* Golden ratio for panel width */
          min-width: 320px;
          max-width: 420px;
          display: flex;
          flex-direction: column;
          background-color: var(--color-surface);
          border: 1px solid var(--color-border-strong);
          border-radius: 4px;
          overflow: hidden;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        }
        
        .panel-header {
          display: flex;
          flex-direction: column;
          gap: 8px;
          padding: 12px 16px;
          background-color: var(--color-surface-raised);
          border-bottom: 1px solid var(--color-border);
          min-height: 92px;
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
          flex: 1;
          overflow-y: auto;
          padding: 8px;
          min-height: 0; /* Required for Firefox */
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
