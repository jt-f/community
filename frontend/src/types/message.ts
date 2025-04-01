export interface ChatMessage {
  message_id: string;
  sender_id: string;
  receiver_id: string;
  text_payload: string;
  send_timestamp: string;
  message_type: MessageType;
  in_reply_to_message_id?: string; // Optional, only present for reply messages
}

export enum MessageType {
  TEXT = 'TEXT',
  REPLY = 'REPLY',
  SYSTEM = 'SYSTEM',
  ERROR = 'ERROR',
  AGENT_STATUS_UPDATE = 'AGENT_STATUS_UPDATE',
  REGISTER_FRONTEND = 'REGISTER_FRONTEND'
}

export interface AgentStatus {
  agent_id: string;
  agent_name: string;
  is_online: boolean;
  last_seen: string;
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
  in_reply_to_message_id?: string
): ChatMessage {
  return {
    message_id: Math.random().toString(36).substring(2, 8),
    sender_id,
    receiver_id,
    text_payload,
    send_timestamp: new Date().toLocaleTimeString(),
    message_type,
    ...(in_reply_to_message_id && { in_reply_to_message_id })
  };
} 