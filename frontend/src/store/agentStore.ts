import { create } from 'zustand';
import { AgentStatus, AgentWithMetrics } from '../types/message';

interface AgentStore {
  agents: AgentStatus[];
  updateAgents: (newAgents: AgentWithMetrics[], isFullUpdate: boolean) => void;
  getAgentById: (agentId: string) => AgentStatus | undefined;
  getOnlineAgents: () => AgentStatus[];
  getOfflineAgents: () => AgentStatus[];
  getAgentCount: () => number;
}

// Helper function to convert from new metrics format to AgentStatus format
const convertToAgentStatus = (agentWithMetrics: AgentWithMetrics): AgentStatus => {
  const { agent_id, metrics } = agentWithMetrics;
  const internal_state = metrics.internal_state || 'offline';
  
  return {
    agent_id,
    agent_name: metrics.agent_name || 'Unknown Agent',
    last_seen: metrics.last_seen || new Date().toISOString(),
    is_online: internal_state !== 'offline',
    status: internal_state, // Use internal_state as status field
    metrics: metrics // Keep the original metrics for reference
  };
};

export const useAgentStore = create<AgentStore>((set, get) => ({
  agents: [],
  
  updateAgents: (newAgents: AgentWithMetrics[], isFullUpdate: boolean) => {
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
    return get().agents.filter(agent => agent.is_online);
  },
  
  getOfflineAgents: () => {
    return get().agents.filter(agent => !agent.is_online);
  },
  
  getAgentCount: () => {
    return get().agents.length;
  }
})); 