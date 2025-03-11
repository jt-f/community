export interface WebSocketMessage {
  type: string;
  data: {
    agents?: any[];
    [key: string]: any;
  };
} 