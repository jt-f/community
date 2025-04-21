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
            agents.map(agent => {
                const internalState = agent.metrics?.internal_state || 'offline';
                let statusClass = '';
                switch (internalState) {
                    case 'idle':
                        statusClass = 'idle';
                        break;
                    case 'initializing':
                        statusClass = 'initializing';
                        break;
                    case 'working':
                        statusClass = 'working';
                        break;
                    case 'paused':
                        statusClass = 'paused';
                        break;
                    case 'offline':
                        statusClass = 'offline';
                        break;
                    default:
                        statusClass = 'unknown';
                }

                return (
                    <div key={agent.agent_id} className="agent-item">
                        <div className="agent-header">
                            <div className="agent-name-container">
                                <div className={`status-indicator ${statusClass}`}></div>
                                <div className="agent-identity">
                                    <span className="agent-name" title={agent.agent_id}>{agent.agent_name}</span>
                                    {showId && <span className="agent-id">ID: {agent.agent_id.substring(0, 8)}</span>}
                                </div>
                            </div>
                            <div className="agent-actions">
                                {onPauseToggle && (
                                    <button
                                        onClick={() => onPauseToggle(agent)}
                                        className="icon-btn"
                                        title={
                                            internalState === 'offline'
                                                ? 'Resume Agent'
                                                : internalState === 'paused'
                                                    ? 'Resume Agent'
                                                    : 'Pause Agent'
                                        }
                                    >
                                        {internalState === 'offline' || internalState === 'paused' ? (
                                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="5 3 19 12 5 21 5 3" /></svg>
                                        ) : (
                                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></svg>
                                        )}
                                    </button>
                                )}
                                {onDeregisterToggle && (
                                    <button
                                        onClick={() => onDeregisterToggle(agent)}
                                        className="icon-btn"
                                        title={internalState !== 'offline' ? 'Deregister Agent' : 'Reregister Agent'}
                                    >
                                        {internalState !== 'offline' ? (
                                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6L6 18" /><path d="M6 6l12 12" /></svg>
                                        ) : (
                                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="1 4 1 10 7 10" /><polyline points="23 20 23 14 17 14" /><path d="M20.49 9A9 9 0 0 0 5.51 15M3.51 9A9 9 0 0 1 18.49 15" /></svg>
                                        )}
                                    </button>
                                )}
                            </div>
                        </div>
                        <div className="agent-meta">
                            <div className="status-info">
                                <span className="last-seen">Last seen: {agent.last_seen ? new Date(agent.last_seen).toLocaleString() : 'Never'}</span>
                                <span className="status-text">{internalState}</span>
                            </div>
                            <div className="agent-subsystem-statuses">
                                {renderSubsystemStatus(agent.metrics, 'message_queue_status', 'Message Queue')}
                                {renderSubsystemStatus(agent.metrics, 'grpc_status', 'Server Connection')}
                                {renderSubsystemStatus(agent.metrics, 'llm_client_status', 'AI Service')}
                                {renderSubsystemStatus(agent.metrics, 'registration_status', 'Registration')}
                            </div>
                        </div>
                    </div>
                );
            })
        )}
        <style>
            {`
                .agent-item {
                    position: relative;
                    background: var(--color-surface-raised);
                    border-radius: 6px;
                    padding: 12px;
                    margin-bottom: 8px;
                    transition: all 0.2s ease;
                }

                .agent-item:hover {
                    transform: translateY(-1px);
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                }

                .agent-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: flex-start;
                    margin-bottom: 8px;
                }

                .agent-name-container {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }

                .agent-identity {
                    display: flex;
                    flex-direction: column;
                }

                .agent-name {
                    font-weight: 500;
                    font-size: 14px;
                }

                .agent-id {
                    font-size: 12px;
                    color: var(--color-text-muted);
                }

                .agent-actions {
                    display: flex;
                    gap: 4px;
                }

                .agent-meta {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    font-size: 12px;
                    color: var(--color-text-muted);
                    margin-top: 8px;
                }

                .status-info {
                    display: flex;
                    gap: 12px;
                    align-items: center;
                }

                .status-text {
                    font-weight: 500;
                }

                .agent-subsystem-statuses {
                    display: flex;
                    gap: 8px;
                    align-items: center;
                }

                .subsystem-status {
                    display: inline-flex;
                    align-items: center;
                }

                .status-indicator {
                    width: 8px;
                    height: 8px;
                    border-radius: 50%;
                    flex-shrink: 0;
                }

                .status-indicator.idle {
                    background-color: #4caf50;
                    box-shadow: 0 0 4px #4caf50;
                }
                .status-indicator.initializing {
                    background-color: #ff9800;
                    box-shadow: 0 0 4px #ff9800;
                }
                .status-indicator.working {
                    background-color: #2196f3;
                    box-shadow: 0 0 4px #2196f3;
                }
                .status-indicator.paused {
                    background-color: #ffd600;
                    box-shadow: 0 0 4px #ffd600;
                    animation: pulse 2s infinite;
                }
                .status-indicator.offline {
                    background-color: #f44336;
                    box-shadow: 0 0 4px #f44336;
                }
                .status-indicator.unknown {
                    background-color: #fff;
                    border: 1.5px solid #bbb;
                    box-shadow: 0 0 4px #bbb;
                }
                @keyframes pulse {
                    0% { opacity: 0.5; }
                    50% { opacity: 1; }
                    100% { opacity: 0.5; }
                }
            `}
        </style>
    </div>
);

// Helper for subsystem status icons
function renderSubsystemStatus(metrics: Record<string, string> = {}, key: string, label: string) {
    const value = (metrics && metrics[key]) || '';
    let ok = false;
    if (key === 'registration_status') {
        ok = value === 'registered';
    } else if (key === 'llm_client_status') {
        ok = value === 'configured' || value === 'connected';
    } else {
        ok = value === 'connected';
    }
    return (
        <span className="subsystem-status" title={`${label}: ${value || 'unknown'}`}
            style={{ marginLeft: 6, display: 'inline-flex', alignItems: 'center' }}>
            {ok ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#4caf50" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
            ) : (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f44336" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
            )}
        </span>
    );
}
