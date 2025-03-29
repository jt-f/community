import { useAgentStore } from '../store/agentStore';
import { useMessageStore } from '../store/messageStore';
import { generateShortId } from './idGenerator';

// Convert from old message format to new format
const convertToMessageStoreFormat = (message: any) => {
  // Extract message_id safely
  const messageId = message.message_id || message.id || generateShortId();
  
  // Extract sender_id safely
  let senderId;
  if (message.data?.message?.sender_id) {
    senderId = message.data.message.sender_id;
  } else if (message.message?.sender_id) {
    senderId = message.message.sender_id;
  } else {
    senderId = message.sender_id || 'unknown';
  }
  
  // Extract receiver_id safely
  let receiverId;
  if (message.data?.message?.receiver_id) {
    receiverId = message.data.message.receiver_id;
  } else if (message.message?.receiver_id) {
    receiverId = message.message.receiver_id;
  } else {
    receiverId = message.receiver_id;
  }
  
  // Extract timestamp safely
  const timestamp = message.timestamp || 
    message.message?.timestamp || 
    message.data?.timestamp || 
    message.data?.message?.timestamp || 
    new Date().toISOString();
  
  // Extract content safely
  let content: any = { text: 'No content available' };
  try {
    if (message.data?.message?.content) {
      content = message.data.message.content;
    } else if (message.message?.content) {
      content = message.message.content;
    } else if (message.content) {
      content = message.content;
    }
    
    // If content is a string, convert to object
    if (typeof content === 'string') {
      content = { text: content };
    }
  } catch (e) {
    console.error('Error extracting content:', e);
  }
  
  // Extract message_type safely
  const messageType = message.message_type || 
    message.message?.message_type || 
    message.data?.message?.message_type || 
    'text';
  
  // Determine if message is outgoing
  const isOutgoing = message.type === 'outgoing';
  
  // Extract in_reply_to
  const inReplyTo = message.in_reply_to || 
    message.message?.in_reply_to || 
    message.data?.message?.in_reply_to || 
    content.in_reply_to || 
    undefined;
  
  return {
    message_id: messageId,
    timestamp,
    sender_id: senderId,
    receiver_id: receiverId,
    in_reply_to: inReplyTo,
    content,
    message_type: messageType,
    is_outgoing: isOutgoing
  };
};

// This function migrates data from agentStore to messageStore
export const migrateMessageHistory = () => {
  const agentStore = useAgentStore.getState();
  const messageStore = useMessageStore.getState();
  
  // Skip migration if message store already has data
  if (messageStore.messages.length > 0) {
    console.log('Message store already has data, skipping migration');
    return;
  }
  
  // Get all messages from agent store
  const oldMessages = agentStore.messages;
  console.log(`Migrating ${oldMessages.length} messages from agent store to message store`);
  
  // Convert and add each message to the new store
  oldMessages.forEach(message => {
    const convertedMessage = convertToMessageStoreFormat(message);
    try {
      messageStore.addMessage(convertedMessage);
    } catch (e) {
      console.error('Error migrating message:', e, message, convertedMessage);
    }
  });
  
  console.log(`Migration complete: ${messageStore.messages.length} messages in message store`);
};

// This function should be called once on app initialization
export const initializeMessageStore = () => {
  migrateMessageHistory();
}; 