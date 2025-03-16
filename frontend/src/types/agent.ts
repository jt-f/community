export interface Agent {
  id: string;
  name: string;
  type: string;
  status: 'idle' | 'responding' | 'thinking';
  capabilities: string[];
  model?: string;
  provider?: string;
} 