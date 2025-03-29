import { v4 as uuidv4 } from 'uuid';

/**
 * Generates a short unique message ID
 * This creates a shorter ID than a full UUID while still being unique enough for our purposes
 * @returns A short unique ID string (8-12 chars)
 */
export const generateShortId = (): string => {
  // Generate a full UUID
  const fullUuid = uuidv4();
  
  // Take just the first segment of the UUID (8 chars) and add a timestamp component
  const firstSegment = fullUuid.split('-')[0];
  
  // Add a timestamp component for additional uniqueness (last 4 digits of current timestamp)
  const timestampPart = Date.now().toString().slice(-4);
  
  // Combine for a short but unique ID
  return `${firstSegment}-${timestampPart}`;
}; 