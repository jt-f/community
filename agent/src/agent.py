import pika
import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import uuid
import websockets
from typing import Dict, Any, Optional, Callable
from datetime import datetime


from shared_models import (
    MessageType,
    ResponseStatus,
    ChatMessage,
    AgentRegistrationMessage,
    AgentRegistrationResponse,
    create_text_message,
    create_reply_message
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Reduce verbosity from pika library
logging.getLogger("pika").setLevel(logging.WARNING)
logger.info("Pika library logging level set to WARNING.")

class Agent:
    def __init__(self, agent_id: str, agent_name: str, websocket_url: str, rabbitmq_host: str):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.websocket_url = websocket_url
        self.rabbitmq_host = rabbitmq_host
        self.websocket = None
        self.rabbitmq_connection = None
        self.rabbitmq_channel = None
        self.queue_name = f"agent_queue_{self.agent_id}"
        self.is_registered = False
        self.running = False
        
    async def connect_websocket(self) -> bool:
        """Connect to WebSocket server for status updates and ping/pong."""
        try:
            logger.info(f"Agent {self.agent_name} connecting to WebSocket for status updates at {self.websocket_url}...")
            self.websocket = await websockets.connect(self.websocket_url)
            logger.info(f"Connected to WebSocket server for status updates")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            return False
            
    def connect_rabbitmq(self) -> bool:
        """Connect to RabbitMQ server for message processing."""
        try:
            logger.info(f"Connecting to RabbitMQ at {self.rabbitmq_host} for message processing...")
            self.rabbitmq_connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=self.rabbitmq_host)
            )
            self.rabbitmq_channel = self.rabbitmq_connection.channel()
            logger.info("Connected to RabbitMQ")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            return False
            
    async def register_with_server(self) -> bool:
        """Register the agent with the server via WebSocket.
        
        This registers both the WebSocket connection for status updates
        and the message queue for processing.
        """
        if not self.websocket:
            logger.error("Cannot register: WebSocket connection not established")
            return False
            
        try:
            # Create registration message with just the name
            registration_message = {
                "message_type": MessageType.REGISTER_AGENT,
                "agent_name": self.agent_name
            }
            await self.websocket.send(json.dumps(registration_message))
            logger.info(f"Sent registration request to server")

            # Wait for confirmation response
            response = await self.websocket.recv()
            response_data = json.loads(response)
            logger.info(f"Registration response: {response_data}")
            
            # Process response
            if (response_data.get("message_type") == MessageType.REGISTER_AGENT_RESPONSE and 
                response_data.get("status") == ResponseStatus.SUCCESS):
                # Store the assigned agent ID
                self.agent_id = response_data["agent_id"]
                logger.info(f"Agent {self.agent_name} successfully registered with ID: {self.agent_id}")
                self.is_registered = True
                return True
            else:
                error_msg = response_data.get("text_payload", "Unknown error during registration")
                logger.error(f"Registration failed: {error_msg}")
                return False
                
        except Exception as e:
            logger.error(f"Error during registration: {e}")
            return False
    
    def setup_rabbitmq_queue(self) -> bool:
        """Set up the RabbitMQ queue for receiving messages."""
        if not self.rabbitmq_channel:
            logger.error("Cannot setup queue: RabbitMQ connection not established")
            return False
            
        try:
            # Declare a queue for this agent
            self.rabbitmq_channel.queue_declare(queue=self.queue_name, durable=True)
            
            # Set up a consumer with callback
            self.rabbitmq_channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=self.process_rabbitmq_message,
                auto_ack=False  # We'll acknowledge manually after processing
            )
            
            logger.info(f"RabbitMQ queue {self.queue_name} set up successfully for message processing")
            return True
        except Exception as e:
            logger.error(f"Failed to set up RabbitMQ queue: {e}")
            return False
    
    def publish_to_broker_input_queue(self, message_data: dict) -> bool:
        """Publish a response message to the broker input queue."""
        if not self.rabbitmq_channel:
            logger.error("Cannot publish: RabbitMQ connection not established")
            return False
            
        try:
            # Ensure the queue exists
            self.rabbitmq_channel.queue_declare(queue="broker_input_queue", durable=True)
            
            # Publish the message
            self.rabbitmq_channel.basic_publish(
                exchange='',
                routing_key="broker_input_queue",
                body=json.dumps(message_data),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # make message persistent
                )
            )
            
            logger.info(f"Published message {message_data} to broker_input_queue")
            return True
        except Exception as e:
            logger.error(f"Failed to publish to broker_input_queue: {e}")
            return False
    
    def process_rabbitmq_message(self, ch, method, properties, body):
        """Process a message received from RabbitMQ queue."""
        try:
            # Parse the message
            message_dict = json.loads(body)
            
            # Log the received message
            message_type = message_dict.get("message_type", "unknown")
            message_id = message_dict.get("message_id", "unknown")
            sender_id = message_dict.get("sender_id", "unknown")
            logger.info(f"Received message type={message_type}, id={message_id} from {sender_id} via queue")
            
            # Process the message and generate response
            response = self.generate_response(message_dict)
            
            # Send response back through broker_input_queue
            if self.publish_to_broker_input_queue(response):
                logger.info(f"Sent response to message {message_id} via broker_input_queue")
            else:
                logger.error(f"Failed to send response to message {message_id}")
            
            # Acknowledge the message
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except json.JSONDecodeError:
            logger.error("Received invalid JSON in queue message")
            # Reject the message
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            logger.error(f"Error processing queue message: {e}")
            # Requeue the message for later processing
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    def generate_response(self, message) -> dict:
        """Generate a response for a received message."""
        # Default implementation - create a simple response
        # In a real application, this method would contain agent-specific logic
        
        if isinstance(message, dict):
            sender_id = message.get("sender_id", "unknown")
            text_payload = message.get("text_payload", "")
            message_id = message.get("message_id", None)
            
            # Create a response dictionary
            response = {
                "message_type": MessageType.REPLY,
                "sender_id": self.agent_id,
                "receiver_id": sender_id,
                "text_payload": f"Dummy response to '{text_payload}'",
                "timestamp": datetime.now().isoformat()
            }
            
            # Add reference to original message if available
            if message_id:
                response["in_reply_to"] = message_id
                
            return response
        else:
            # Create a generic response for non-dict messages
            return {
                "message_type": MessageType.TEXT,
                "sender_id": self.agent_id,
                "receiver_id": "unknown",
                "text_payload": f"Agent {self.agent_name} received a message",
                "timestamp": datetime.now().isoformat()
            }

    async def listen_websocket(self) -> None:
        """Listen for status updates and control messages from the WebSocket server."""
        if not self.websocket:
            logger.error("Cannot listen: WebSocket connection not established")
            return
            
        try:
            async for message in self.websocket:
                data = json.loads(message)
                message_type = data.get("message_type")
                
                if message_type == MessageType.PING:
                    # Respond to ping with a pong for status tracking
                    server_ping_time = data.get("timestamp", "unknown")
                    response_time = datetime.now().isoformat()
                    logger.info(f"Received PING from server, responding with PONG")
                    
                    await self.websocket.send(json.dumps({
                        "message_type": MessageType.PONG,
                        "agent_id": self.agent_id,
                        "agent_name": self.agent_name,
                        "response_time": response_time,
                        "server_ping_time": server_ping_time
                    }))
                elif message_type == MessageType.SHUTDOWN:
                    # Handle shutdown request
                    logger.info("Received shutdown request from server")
                    self.running = False
                    break
                elif message_type == MessageType.AGENT_STATUS_UPDATE:
                    # Agent status broadcasts can be ignored
                    logger.debug("Received agent status update, ignoring as it's meant for frontend clients")
                else:
                    # Log other messages received on WebSocket
                    logger.info(f"Received message type {message_type} on WebSocket (should be using queue)")
                    
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"WebSocket connection closed: {e}")
        except Exception as e:
            logger.error(f"Error in WebSocket listener: {e}")
    
    def start_rabbitmq_consumer(self) -> None:
        """Start consuming messages from the RabbitMQ queue."""
        if not self.rabbitmq_channel:
            logger.error("Cannot start consumer: RabbitMQ connection not established")
            return
            
        try:
            logger.info(f"Starting to consume messages from queue {self.queue_name}")
            self.rabbitmq_channel.start_consuming()
        except Exception as e:
            logger.error(f"Error in RabbitMQ consumer: {e}")
    
    async def run(self) -> None:
        """Run the agent's main loop with the hybrid approach:
        - WebSockets for status updates and ping/pong
        - RabbitMQ queues for message processing
        """
        self.running = True
        
        # Connect to WebSocket for status updates
        if not await self.connect_websocket():
            logger.error("Failed to connect to WebSocket server. Exiting.")
            return
        
        # Register with server (sets up both WebSocket and queue)
        if not await self.register_with_server():
            logger.error("Failed to register with server. Exiting.")
            return
        
        # Connect to RabbitMQ for message processing
        if not self.connect_rabbitmq():
            logger.error("Failed to connect to RabbitMQ. Exiting.")
            return
        
        # Set up RabbitMQ queue for receiving messages
        if not self.setup_rabbitmq_queue():
            logger.error("Failed to set up RabbitMQ queue. Exiting.")
            return
        
        # Start RabbitMQ consumer in a separate thread for message processing
        import threading
        consumer_thread = threading.Thread(target=self.start_rabbitmq_consumer)
        consumer_thread.daemon = True
        consumer_thread.start()
        logger.info("Started RabbitMQ consumer thread for message processing")
        
        # Listen for status updates and control messages on WebSocket
        try:
            logger.info("Listening for status updates and control messages on WebSocket")
            await self.listen_websocket()
        finally:
            self.cleanup()
    
    def cleanup(self) -> None:
        """Clean up connections before exit."""
        logger.info("Cleaning up before exit...")
        
        # Close WebSocket connection
        if self.websocket:
            try:
                # Create a new event loop for the close task
                close_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(close_loop)
                
                # Create and run a task to close the websocket
                close_loop.run_until_complete(self.close_websocket())
                close_loop.close()
                
                logger.info("WebSocket connection closed")
            except Exception as e:
                logger.error(f"Error closing WebSocket connection: {e}")
        
        # Close RabbitMQ connection
        if self.rabbitmq_connection and self.rabbitmq_connection.is_open:
            try:
                if self.rabbitmq_channel and self.rabbitmq_channel.is_open:
                    self.rabbitmq_channel.stop_consuming()
                self.rabbitmq_connection.close()
                logger.info("RabbitMQ connection closed")
            except Exception as e:
                logger.error(f"Error closing RabbitMQ connection: {e}")
    
    async def close_websocket(self) -> None:
        """Close the websocket connection gracefully."""
        if self.websocket:
            try:
                await self.websocket.close()
                self.websocket = None
                logger.info("Closed WebSocket connection")
            except Exception as e:
                logger.error(f"Error closing WebSocket: {e}")
                self.websocket = None

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run an agent with hybrid communication approach")
    
    parser.add_argument("--id", type=str, help="Unique identifier for this agent")
    parser.add_argument("--name", type=str, required=True, help="Human-readable name for this agent")
    parser.add_argument("--ws-url", type=str, default="ws://localhost:8765/ws", help="WebSocket server URL for status updates")
    parser.add_argument("--rabbitmq-host", type=str, default="localhost", help="RabbitMQ server host for message processing")
    
    return parser.parse_args()

async def main():
    """Main entry point for the agent using the hybrid approach."""
    # Parse command line arguments
    args = parse_arguments()
    
    # Generate a unique ID if not provided
    agent_id = args.id if args.id else f"agent_{uuid.uuid4().hex[:8]}"
    
    # Create and run the agent with the hybrid approach
    agent = Agent(
        agent_id=agent_id,
        agent_name=args.name,
        websocket_url=args.ws_url,
        rabbitmq_host=args.rabbitmq_host
    )
    
    # Handle termination signals
    loop = asyncio.get_event_loop()
    
    def signal_handler():
        logger.info("Received termination signal, shutting down...")
        if agent.running:
            agent.running = False
            # Force cleanup
            agent.cleanup()
            # Cancel all running tasks
            for task in asyncio.all_tasks(loop):
                if task is not asyncio.current_task():
                    task.cancel()
            loop.stop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        logger.info(f"Starting agent {agent.agent_name} (ID: {agent.agent_id}) with hybrid communication")
        logger.info(f"- WebSockets for status updates and pings")
        logger.info(f"- RabbitMQ queues for message processing")
        await agent.run()
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
    finally:
        logger.info("Agent shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
