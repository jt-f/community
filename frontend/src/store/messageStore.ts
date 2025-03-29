import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { generateShortId } from '../utils/idGenerator';
import { getAgentName } from '../utils/agentUtils';

// Define the Message interface
export interface Message {
  message_id: string;
  timestamp: string;
  sender_id: string;
  receiver_id?: string;
  in_reply_to?: string;
  content: {
    text?: string;
    type?: string;
    [key: string]: any;
  };
  message_type: string;
  metadata?: Record<string, any>;
  is_outgoing?: boolean;
}

// Define the MessageThread interface
export interface MessageThread {
  original: Message;
  replies: Message[];
}

// Define the message store interface
interface MessageStore {
  // Message collections
  messages: Message[];
  messagesByID: Record<string, Message>;
  messageThreads: Record<string, MessageThread>;
  
  // Actions
  addMessage: (message: Partial<Message>) => string;
  addReply: (replyTo: string, replyMessage: Partial<Message>) => string;
  updateMessage: (messageId: string, updates: Partial<Message>) => void;
  getThreadForMessage: (messageId: string) => MessageThread | undefined;
  clearHistory: () => void;
  
  // Utility methods
  getEffectiveReceiver: (message: Message) => string | undefined;
}

// Helper function to create a timestamp
const getTimestamp = () => new Date().toISOString();

// Helper function to normalize messages
const normalizeMessage = (message: Partial<Message>): Message => {
  // Generate a unique ID if one wasn't provided
  const messageId = message.message_id || generateShortId();
  
  return {
    message_id: messageId,
    timestamp: message.timestamp || getTimestamp(),
    sender_id: message.sender_id || 'unknown',
    receiver_id: message.receiver_id,
    in_reply_to: message.in_reply_to,
    content: message.content || { text: '' },
    message_type: message.message_type || 'text',
    metadata: message.metadata || {},
    is_outgoing: message.is_outgoing || false
  };
};

// Create the message store
export const useMessageStore = create<MessageStore>()(
  persist(
    (set, get) => ({
      messages: [],
      messagesByID: {},
      messageThreads: {},

      addMessage: (message: Partial<Message>) => {
        const normalizedMessage = normalizeMessage(message);
        const messageId = normalizedMessage.message_id;

        // Check if this message already exists
        if (get().messagesByID[messageId]) {
          console.log(`Message ${messageId} already exists, skipping`);
          return messageId;
        }

        // Update state
        set((state) => {
          // Add to messages array
          const newMessages = [...state.messages, normalizedMessage];
          
          // Add to messagesByID map
          const newMessagesById = {
            ...state.messagesByID,
            [messageId]: normalizedMessage
          };
          
          // If it's a reply, update or create the thread
          let newThreads = { ...state.messageThreads };
          
          if (normalizedMessage.in_reply_to) {
            const originalMessageId = normalizedMessage.in_reply_to;
            
            if (state.messagesByID[originalMessageId]) {
              // Original message exists, add to existing thread or create new thread
              if (state.messageThreads[originalMessageId]) {
                // Thread exists, add this reply
                newThreads[originalMessageId] = {
                  ...state.messageThreads[originalMessageId],
                  replies: [...state.messageThreads[originalMessageId].replies, normalizedMessage]
                };
              } else {
                // Create new thread
                newThreads[originalMessageId] = {
                  original: state.messagesByID[originalMessageId],
                  replies: [normalizedMessage]
                };
              }
            }
          }

          return {
            messages: newMessages,
            messagesByID: newMessagesById,
            messageThreads: newThreads
          };
        });

        return messageId;
      },

      addReply: (replyTo: string, replyMessage: Partial<Message>) => {
        // Make sure the reply has the in_reply_to field set
        const messageWithReplyInfo = {
          ...replyMessage,
          in_reply_to: replyTo
        };

        // Use the addMessage function to add the reply
        return get().addMessage(messageWithReplyInfo);
      },

      updateMessage: (messageId: string, updates: Partial<Message>) => {
        set((state) => {
          // Check if message exists
          if (!state.messagesByID[messageId]) {
            console.warn(`Message ${messageId} not found, cannot update`);
            return state;
          }

          // Create updated message
          const updatedMessage = {
            ...state.messagesByID[messageId],
            ...updates,
            message_id: messageId // Ensure ID doesn't change
          };

          // Update in messages array
          const messageIndex = state.messages.findIndex(m => m.message_id === messageId);
          const newMessages = [...state.messages];
          if (messageIndex >= 0) {
            newMessages[messageIndex] = updatedMessage;
          }

          // Update in messagesByID map
          const newMessagesById = {
            ...state.messagesByID,
            [messageId]: updatedMessage
          };

          // Update in threads if needed
          let newThreads = { ...state.messageThreads };
          
          // If this message is an original in a thread
          if (newThreads[messageId]) {
            newThreads[messageId] = {
              ...newThreads[messageId],
              original: updatedMessage
            };
          }
          
          // If this message is a reply in any thread
          Object.keys(newThreads).forEach(threadId => {
            const thread = newThreads[threadId];
            const replyIndex = thread.replies.findIndex(r => r.message_id === messageId);
            
            if (replyIndex >= 0) {
              const newReplies = [...thread.replies];
              newReplies[replyIndex] = updatedMessage;
              
              newThreads[threadId] = {
                ...thread,
                replies: newReplies
              };
            }
          });

          return {
            messages: newMessages,
            messagesByID: newMessagesById,
            messageThreads: newThreads
          };
        });
      },

      getThreadForMessage: (messageId: string) => {
        // Check if message is an original in a thread
        if (get().messageThreads[messageId]) {
          return get().messageThreads[messageId];
        }
        
        // Check if message is a reply in any thread
        const message = get().messagesByID[messageId];
        if (message?.in_reply_to) {
          return get().messageThreads[message.in_reply_to];
        }
        
        return undefined;
      },

      clearHistory: () => {
        set({
          messages: [],
          messagesByID: {},
          messageThreads: {}
        });
      },

      getEffectiveReceiver: (message: Message) => {
        // If there's a direct receiver that's not broadcast, use it
        if (message.receiver_id && message.receiver_id !== 'broadcast') {
          return message.receiver_id;
        }
        
        // For broadcast messages that are replies, use the original sender
        if (message.receiver_id === 'broadcast' && message.in_reply_to) {
          const originalMessage = get().messagesByID[message.in_reply_to];
          if (originalMessage) {
            return originalMessage.sender_id;
          }
        }
        
        // Otherwise, return the broadcast or undefined
        return message.receiver_id;
      }
    }),
    {
      name: 'message-store', // name for localStorage
      partialize: (state) => ({
        // Only persist these parts of the state
        messages: state.messages,
        messagesByID: state.messagesByID,
        messageThreads: state.messageThreads
      }),
    }
  )
); 