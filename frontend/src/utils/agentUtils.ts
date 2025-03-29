import { Agent } from '../types/agent';

/**
 * Gets the display name for an agent based on its ID
 * @param agentId - The ID of the agent
 * @param agents - Object or array of agents
 * @returns The display name of the agent
 */
export const getAgentName = (agentId?: string, agents?: Record<string, Agent> | Agent[]): string => {
  if (!agentId) return 'Unknown';
  
  // Check if it's a user ID
  if (agentId.startsWith('user-')) {
    return 'You';
  }
  
  // Find the agent in the agents object
  if (agents && typeof agents === 'object') {
    // If agents is an object with agent IDs as keys
    if (!Array.isArray(agents) && agents[agentId] && agents[agentId].name) {
      return agents[agentId].name;
    }
    
    // If agents is an array-like object, try to find the agent by ID
    if (Array.isArray(agents) || 'find' in agents) {
      const agentArray = Array.isArray(agents) ? agents : Object.values(agents);
      const agent = agentArray.find((a: Agent) => a.id === agentId);
      if (agent && agent.name) {
        return agent.name;
      }
    }
  }
  
  // If we can't find the agent, return a formatted version of the ID
  return `Agent ${agentId.substring(0, 6)}...`;
};

export const isHumanAgent = (agent: any): boolean => {
  return agent?.type?.toLowerCase() === 'human';
};

export const isSystemAgent = (agent: any): boolean => {
  return agent?.type?.toLowerCase() === 'system';
};

export const isAIAgent = (agent: any): boolean => {
  return agent?.type?.toLowerCase() === 'ai';
}; 