import React from 'react';
import { AgentStatus } from '../types/message';

interface AgentListProps {
    agents: AgentStatus[];
    showId?: boolean;
    emptyText?: string;
}

export const AgentList: React.FC<AgentListProps> = ({ agents, showId = false, emptyText = 'No agents found' }) => (
    <div className="agents-list">
        {agents.length === 0 ? (
            <div className="no-agents">{emptyText}</div>
        ) : (
            agents.map(agent => (
                <div key={agent.agent_id} className="agent-item">
                    <div className="agent-info">
                        <div className="agent-name-container">
                            <div className={`status-indicator ${agent.is_online ? 'online' : 'offline'}`}></div>
                            <span className="agent-name" title={agent.agent_id}>{agent.agent_name}</span>
                        </div>
                        {showId && <span className="agent-id">ID: {agent.agent_id.substring(0, 8)}</span>}
                    </div>
                    <div className="agent-meta">
                        <span className="last-seen">Last seen: {agent.last_seen ? new Date(agent.last_seen).toLocaleString() : 'Never'}</span>
                        <span className="status-text">{agent.is_online ? 'Online' : 'Offline'}</span>
                    </div>
                </div>
            ))
        )}
    </div>
);
