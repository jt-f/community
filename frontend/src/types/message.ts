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
  TEXT = 'TEXT',
  REPLY = 'REPLY',
  SYSTEM = 'SYSTEM',
  ERROR = 'ERROR',
  AGENT_STATUS_UPDATE = 'AGENT_STATUS_UPDATE',
  REGISTER_FRONTEND = 'REGISTER_FRONTEND',
  REGISTER_FRONTEND_RESPONSE = 'REGISTER_FRONTEND_RESPONSE',
  REGISTER_AGENT_RESPONSE = 'REGISTER_AGENT_RESPONSE',
  // --- Custom system control types ---
  PAUSE_AGENT = 'PAUSE_AGENT',
  RESUME_AGENT = 'RESUME_AGENT',
  DEREGISTER_AGENT = 'DEREGISTER_AGENT',
  REREGISTER_AGENT = 'REREGISTER_AGENT',
  PAUSE_ALL_AGENTS = 'PAUSE_ALL_AGENTS',
  RESUME_ALL_AGENTS = 'RESUME_ALL_AGENTS',
  DEREGISTER_ALL_AGENTS = 'DEREGISTER_ALL_AGENTS',
  REREGISTER_ALL_AGENTS = 'REREGISTER_ALL_AGENTS',
  RESET_ALL_QUEUES = 'RESET_ALL_QUEUES',
}

export interface AgentStatus {
  agent_id: string;
  agent_name: string;
  is_online: boolean;
  last_seen: string;
  status?: string; // Add status field (online, paused, offline)
}

export interface AgentStatusUpdateMessage {
  message_type: MessageType.AGENT_STATUS_UPDATE;
  agents: AgentStatus[];
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