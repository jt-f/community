export interface ChatMessage {
  message_id: string;
  sender_id: string;
  receiver_id: string;
  text_payload: string;
  send_timestamp: string;
  message_type: MessageType;
  in_reply_to_message_id?: string; // Optional, only present for reply messages
  client_id?: string;
}

export enum MessageType {
  TEXT = "TEXT",
  REPLY = "REPLY",
  SYSTEM = "SYSTEM",
  ERROR = "ERROR",
  AGENT_STATUS_UPDATE = "AGENT_STATUS_UPDATE",
  PAUSE_AGENT = "PAUSE_AGENT",
  RESUME_AGENT = "RESUME_AGENT",
  PAUSE_ALL_AGENTS = "PAUSE_ALL_AGENTS",
  RESUME_ALL_AGENTS = "RESUME_ALL_AGENTS",
  DEREGISTER_AGENT = "DEREGISTER_AGENT",
  REREGISTER_AGENT = "REREGISTER_AGENT",
  DEREGISTER_ALL_AGENTS = "DEREGISTER_ALL_AGENTS",
  REREGISTER_ALL_AGENTS = "REREGISTER_ALL_AGENTS",
  RESET_ALL_QUEUES = "RESET_ALL_QUEUES",
  REGISTER_FRONTEND = "REGISTER_FRONTEND"
}

export interface AgentMetrics {
  agent_name: string;
  last_seen: string;
  internal_state: string;
  [key: string]: any; // Allow for additional metrics
}

export interface AgentWithMetrics {
  agent_id: string;
  metrics: AgentMetrics;
}

export interface AgentStatus {
  agent_id: string;
  agent_name: string;
  last_seen: string;
  internal_state: string;
  metrics: AgentMetrics;
}

export interface AgentStatusUpdateMessage {
  message_type: MessageType.AGENT_STATUS_UPDATE;
  agents: AgentStatus[];
  is_full_update: boolean;
}

// Helper function to create a new message
export function createMessage(
  sender_id: string,
  receiver_id: string,
  text_payload: string,
  message_type: MessageType = MessageType.TEXT,
  in_reply_to_message_id?: string,
  client_id?: string
): ChatMessage {
  return {
    message_id: Math.random().toString(36).substring(2, 8),
    sender_id,
    receiver_id,
    text_payload,
    send_timestamp: new Date().toLocaleTimeString(),
    message_type,
    in_reply_to_message_id,
    client_id
  };
}