import { create } from 'zustand';
import { AgentStatus } from '../types/message';

interface AgentStore {
  agents: AgentStatus[];
  updateAgents: (newAgents: AgentStatus[]) => void;
  getAgentById: (agentId: string) => AgentStatus | undefined;
  getOnlineAgents: () => AgentStatus[];
  getOfflineAgents: () => AgentStatus[];
  getAgentCount: () => number;
}

export const useAgentStore = create<AgentStore>((set, get) => ({
  agents: [],
  
  updateAgents: (newAgents: AgentStatus[]) => {
    set({ agents: newAgents });
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