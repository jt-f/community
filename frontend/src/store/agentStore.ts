import { create } from 'zustand';
import { AgentStatus } from '../types/message';

interface AgentStore {
  agents: AgentStatus[];
  updateAgents: (newAgents: AgentStatus[], isFullUpdate: boolean) => void;
  getAgentById: (agentId: string) => AgentStatus | undefined;
  getOnlineAgents: () => AgentStatus[];
  getOfflineAgents: () => AgentStatus[];
  getAgentCount: () => number;
}

export const useAgentStore = create<AgentStore>((set, get) => ({
  agents: [],
  
  updateAgents: (newAgents: AgentStatus[], isFullUpdate: boolean) => {
    if (isFullUpdate) {
      // For full updates, replace the entire list
      set({ agents: newAgents });
    } else {
      // For delta updates, update or add each agent
      set((state) => {
        const updatedAgents = [...state.agents];
        newAgents.forEach((newAgent) => {
          const index = updatedAgents.findIndex(a => a.agent_id === newAgent.agent_id);
          if (index >= 0) {
            updatedAgents[index] = newAgent;
          } else {
            updatedAgents.push(newAgent);
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