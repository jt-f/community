import { useMessageStore } from '../store/messageStore';

// Function to find the reply chain for a given message
export const getReplyChain = (messageId: string) => {
  const messageStore = useMessageStore.getState();
  const message = messageStore.messagesByID[messageId];
  
  if (!message) return [];
  
  const chain = [message];
  let currentMessage = message;
  
  // Find predecessors (messages this one is replying to)
  while (currentMessage.in_reply_to) {
    const parent = messageStore.messagesByID[currentMessage.in_reply_to];
    if (!parent) break;
    chain.unshift(parent); // Add to beginning of chain
    currentMessage = parent;
  }
  
  // Find direct replies to this message (only immediate replies)
  const directReplies = messageStore.messages.filter(
    (msg) => msg.in_reply_to === messageId
  );
  
  // Add direct replies to chain
  chain.push(...directReplies);
  
  return chain;
};

// Function to determine UI styles for reply visualization
export const getReplyStyles = (message: any, index: number) => {
  const isOutgoing = message.is_outgoing || 
    message.sender_id === localStorage.getItem('userId');
  
  // Base styles
  const styles: any = {
    paper: {},
    sender: {},
    content: {}
  };
  
  // If message is part of a reply chain, add visual cues
  if (message.in_reply_to) {
    styles.paper = {
      ...styles.paper,
      position: 'relative',
      // Add left or right indicator based on outgoing status
      ...(isOutgoing 
        ? { borderLeft: '3px solid rgba(0, 150, 255, 0.5)' }
        : { borderLeft: '3px solid rgba(0, 255, 65, 0.5)' }),
      // Add more spacing to show hierarchy
      ml: isOutgoing ? 0 : 2,
      mr: isOutgoing ? 2 : 0,
    };
    
    // Add reply indicator
    styles.sender = {
      ...styles.sender,
      '&::before': {
        content: '"↩"',
        marginRight: '4px',
        color: isOutgoing ? 'rgba(0, 150, 255, 0.8)' : 'rgba(0, 255, 65, 0.8)',
      }
    };
  }
  
  // Return combined styles
  return styles;
};

// Function to enhance message object with reply metadata
export const enhanceMessageWithReplyData = (message: any) => {
  const messageStore = useMessageStore.getState();
  
  // Skip if message already has reply data
  if (message.hasReplyData) return message;
  
  // Check if this is a reply
  let isReply = false;
  let replyDepth = 0;
  
  if (message.in_reply_to) {
    isReply = true;
    
    // Calculate reply depth
    let currentId = message.in_reply_to;
    while (currentId) {
      replyDepth++;
      const parentMsg = messageStore.messagesByID[currentId];
      if (!parentMsg || !parentMsg.in_reply_to) break;
      currentId = parentMsg.in_reply_to;
    }
  }
  
  // Check if has replies
  const hasReplies = messageStore.messages.some(
    (msg) => msg.in_reply_to === message.message_id
  );
  
  return {
    ...message,
    hasReplyData: true,
    isReply,
    replyDepth,
    hasReplies
  };
}; 