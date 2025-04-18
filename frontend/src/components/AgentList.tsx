import React from 'react';
import { AgentStatus } from '../types/message';

interface AgentListProps {
    agents: AgentStatus[];
    showId?: boolean;
    emptyText?: string;
    onPauseToggle?: (agent: AgentStatus) => void;
    onDeregisterToggle?: (agent: AgentStatus) => void;
}

export const AgentList: React.FC<AgentListProps> = ({ agents, showId = false, emptyText = 'No agents found', onPauseToggle, onDeregisterToggle }) => (
    <div className="agents-list">
        {agents.length === 0 ? (
            <div className="no-agents">{emptyText}</div>
        ) : (
            agents.map(agent => (
                <div key={agent.agent_id} className="agent-item">
                    <div className="agent-info">
                        <div className="agent-name-container">
                            <div className={`status-indicator ${agent.is_online ? (agent.status === 'paused' ? 'paused' : 'online') : 'offline'}`}></div>
                            <span className="agent-name" title={agent.agent_id}>{agent.agent_name}</span>
                        </div>
                        {showId && <span className="agent-id">ID: {agent.agent_id.substring(0, 8)}</span>}
                    </div>
                    <div className="agent-meta">
                        <span className="last-seen">Last seen: {agent.last_seen ? new Date(agent.last_seen).toLocaleString() : 'Never'}</span>
                        <span className="status-text">
                            {!agent.is_online 
                                ? 'Offline' 
                                : agent.status === 'paused' 
                                    ? 'Paused' 
                                    : 'Online'}
                        </span>
                    </div>
                    <div className="agent-actions">
                        {onPauseToggle && (
                            <button onClick={() => onPauseToggle(agent)} className="agent-action-btn">
                                {!agent.is_online 
                                    ? 'Unpause' 
                                    : agent.status === 'paused' 
                                        ? 'Resume' 
                                        : 'Pause'}
                            </button>
                        )}
                        {onDeregisterToggle && (
                            <button onClick={() => onDeregisterToggle(agent)} className="agent-action-btn">
                                {agent.is_online ? 'Deregister' : 'Reregister'}
                            </button>
                        )}
                    </div>
                </div>
            ))
        )}
        <style>
            {`
                .status-indicator.paused {
                    background-color: #ffa500; /* Orange for paused */
                    animation: pulse 2s infinite;
                }
                
                @keyframes pulse {
                    0% {
                        opacity: 0.5;
                    }
                    50% {
                        opacity: 1;
                    }
                    100% {
                        opacity: 0.5;
                    }
                }
            `}
        </style>
    </div>
);
