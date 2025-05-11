import { create } from 'zustand';
import { AgentStatus, AgentWithMetrics } from '../types/message';

interface AgentStore {
  agents: AgentStatus[];
  updateAgents: (newAgents: AgentWithMetrics[], isFullUpdate: boolean, removeAgentId?: string) => void;
  getAgentById: (agentId: string) => AgentStatus | undefined;
  getOnlineAgents: () => AgentStatus[];
  getOfflineAgents: () => AgentStatus[];
  getAgentCount: () => number;
}

// Helper function to convert from metrics format to AgentStatus format
const convertToAgentStatus = (agentWithMetrics: AgentWithMetrics): AgentStatus => {
  const { agent_id, metrics } = agentWithMetrics;

  return {
    agent_id,
    agent_name: metrics.agent_name || 'Unknown Agent',
    last_seen: metrics.last_seen || new Date().toISOString(),
    internal_state: metrics.internal_state || 'offline',
    metrics: metrics // Keep the original metrics for reference
  };
};

export const useAgentStore = create<AgentStore>((set, get) => ({
  agents: [],

  updateAgents: (newAgents: AgentWithMetrics[], isFullUpdate: boolean, removeAgentId?: string) => {
    if (removeAgentId) {
      // Remove a specific agent by ID
      set((state) => ({ agents: state.agents.filter(a => a.agent_id !== removeAgentId) }));
      return;
    }
    if (isFullUpdate) {
      // For full updates, replace the entire list
      const convertedAgents = newAgents.map(convertToAgentStatus);
      set({ agents: convertedAgents });
    } else {
      // For delta updates, update or add each agent
      set((state) => {
        const updatedAgents = [...state.agents];

        newAgents.forEach((newAgent) => {
          const convertedAgent = convertToAgentStatus(newAgent);
          const index = updatedAgents.findIndex(a => a.agent_id === convertedAgent.agent_id);

          if (index >= 0) {
            updatedAgents[index] = convertedAgent;
          } else {
            updatedAgents.push(convertedAgent);
          }
        });

        return { agents: updatedAgents };
      });
    }
  },

  getAgentById: (agentId: string) => {
    return get().agents.find(agent => agent.agent_id === agentId);
  },

  getOnlineAgents: () => {
    return get().agents.filter(agent => agent.internal_state !== 'offline');
  },

  getOfflineAgents: () => {
    return get().agents.filter(agent => agent.internal_state === 'offline');
  },

  getAgentCount: () => {
    return get().agents.length;
  }
}));