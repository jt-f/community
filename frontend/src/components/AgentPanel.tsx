import React, { useState, useEffect, useContext, useMemo } from 'react';
import { useAgentStore } from '../store/agentStore';
import { WebSocketContext } from './ChatUI';
import { AgentList } from './AgentList';
import { AgentStatus, MessageType } from '../types/message';

// Define the AgentPanelProps interface
interface AgentPanelProps {
  wsRef: React.MutableRefObject<WebSocket | null>;
  clientId: string;
  isConnected: boolean;
}

export const AgentPanel: React.FC<AgentPanelProps> = ({ wsRef, clientId, isConnected }) => {
  const { agents, updateAgents, getOnlineAgents, getOfflineAgents } = useAgentStore();
  const [selectedFilter, setSelectedFilter] = useState<'all' | 'online' | 'offline'>('all');
  const { lastMessage, sendMessage } = useContext(WebSocketContext);

  // Process messages from WebSocketContext
  useEffect(() => {
    if (lastMessage && lastMessage.message_type === MessageType.AGENT_STATUS_UPDATE) {
      // Only log full updates or when debugging is needed
      if (lastMessage.is_full_update) {
        console.log('AgentPanel: Received full agent status update');
      }

      // Check if we have the new format or legacy format
      const hasNewFormat = lastMessage.agents.length > 0 && 'metrics' in lastMessage.agents[0];
      console.log(`AgentPanel: Processing ${hasNewFormat ? 'new' : 'legacy'} agent status format`);

      updateAgents(lastMessage.agents, lastMessage.is_full_update);
    }
  }, [lastMessage, updateAgents]);

  // Remove agent from panel if a shutdown/deregister event is received
  useEffect(() => {
    if (lastMessage && (lastMessage.message_type === MessageType.DEREGISTER_AGENT || lastMessage.message_type === MessageType.DEREGISTER_ALL_AGENTS)) {
      if (lastMessage.agent_id) {
        // Remove the agent with the given agent_id
        updateAgents([], false, lastMessage.agent_id);
      } else if (lastMessage.message_type === MessageType.DEREGISTER_ALL_AGENTS) {
        // Remove all agents
        updateAgents([], true);
      }
    }
  }, [lastMessage, updateAgents]);

  // --- System-wide control handlers ---
  const handlePauseAllAgents = () => {
    if (wsRef.current && isConnected) {
      wsRef.current.send(JSON.stringify({
        message_type: MessageType.PAUSE_ALL_AGENTS,
        sender_id: clientId
      }));
    }
  };

  const handleResumeAllAgents = () => {
    if (wsRef.current && isConnected) {
      wsRef.current.send(JSON.stringify({
        message_type: MessageType.RESUME_ALL_AGENTS,
        sender_id: clientId
      }));
    }
  };

  const handleDeregisterAllAgents = () => {
    if (wsRef.current && isConnected) {
      wsRef.current.send(JSON.stringify({
        message_type: MessageType.DEREGISTER_ALL_AGENTS,
        sender_id: clientId
      }));
    }
  };

  // --- Per-agent control handlers ---
  const handlePauseAgent = (agent: AgentStatus) => {
    if (!wsRef.current) return;

    // Use internal_state to determine the command type
    const commandType = agent.internal_state === 'paused' ? MessageType.RESUME_AGENT : MessageType.PAUSE_AGENT;

    const message = {
      message_type: commandType,
      agent_id: agent.agent_id,
      sender_id: clientId
    };

    try {
      wsRef.current.send(JSON.stringify(message));
      console.log(`Sent ${commandType} command for agent ${agent.agent_id}`);
    } catch (error) {
      console.error("Failed to send pause/resume command:", error);
    }
  };

  const handleDeregisterToggle = (agent: AgentStatus) => {
    if (wsRef.current && isConnected) {
      wsRef.current.send(JSON.stringify({
        message_type: agent.internal_state !== 'offline' ? MessageType.DEREGISTER_AGENT : MessageType.REREGISTER_AGENT,
        agent_id: agent.agent_id
      }));
    }
  };

  // Get the agents to display based on selected filter
  const getFilteredAgents = () => {
    return selectedFilter === 'online'
      ? getOnlineAgents()
      : selectedFilter === 'offline'
        ? getOfflineAgents()
        : agents;
  };

  const filteredAgents = getFilteredAgents();

  const handleRefresh = () => {
    if (wsRef.current && isConnected) {
      wsRef.current.send(JSON.stringify({
        message_type: "REQUEST_AGENT_STATUS",
        sender_id: clientId
      }));
    }
  };

  return (
    <div className="agent-panel">
      <div className="panel-header">
        <div className="header-top">
          <h3>Agents</h3>
          <div className="header-controls">
            <div className="connection-status">
              <div
                className={`status-indicator ${isConnected ? 'online' : 'offline'}`}
                title={isConnected ? 'Receiving agent status updates' : 'Not receiving agent status updates'}
              ></div>
              <span className="status-text connectivity-status-text">{isConnected ? 'Receiving agent status updates' : 'Not connected'}</span>
            </div>
            <button className="refresh-button" onClick={handleRefresh} title="Refresh agents">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.3" />
              </svg>
            </button>
          </div>
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
      <AgentList
        agents={filteredAgents}
        onPauseToggle={handlePauseAgent}
        onDeregisterToggle={handleDeregisterToggle}
      />
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
        
        .header-top {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .header-controls {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .refresh-button {
          width: 32px;
          height: 32px;
          padding: 6px;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 4px;
          border: 1px solid var(--color-border);
          background: var(--color-surface);
          cursor: pointer;
          transition: all 0.2s;
        }

        .refresh-button:hover {
          background: var(--color-surface-raised);
          border-color: var(--color-border-strong);
        }

        .refresh-button svg {
          color: #4caf50;
          transition: transform 0.3s ease;
        }

        .refresh-button:hover svg {
          transform: rotate(180deg);
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
        
        .status-text, .connectivity-status-text {
          font-size: 0.75em;
          font-weight: 600;
          color: var(--color-text-secondary);
          letter-spacing: 0.5px;
        }
        
        .last-seen {
          color: var(--color-text-tertiary);
        }
        `}
      </style>
    </div>
  );
}
