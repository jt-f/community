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
        
    async def connect_websocket(self) -> None:
        """Connect to the WebSocket server."""
        try:
            logger.info(f"Agent {self.agent_name} connecting to WebSocket at {self.websocket_url}...")
            self.websocket = await websockets.connect(self.websocket_url)
            logger.info(f"Connected to WebSocket server")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            return False
            
    def connect_rabbitmq(self) -> bool:
        """Connect to RabbitMQ server."""
        try:
            logger.info(f"Connecting to RabbitMQ at {self.rabbitmq_host}...")
            self.rabbitmq_connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=self.rabbitmq_host)
            )
            self.rabbitmq_channel = self.rabbitmq_connection.channel()
            logger.info("Connected to RabbitMQ")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            return False
            
    async def register_with_broker(self) -> bool:
        """Register the agent with the broker via WebSocket."""
        if not self.websocket:
            logger.error("Cannot register: WebSocket connection not established")
            return False
            
        try:
            # Create registration message

            # Use the new AgentRegistrationMessage class
            registration_message = AgentRegistrationMessage(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                message_type=MessageType.REGISTER_AGENT
            )
            await self.websocket.send(json.dumps(registration_message.to_dict()))

            # Wait for confirmation response
            response = await self.websocket.recv()
            response_data = json.loads(response)
            logger.info(f"Registration response: {response_data}")
            
            # Process response

            response_obj = AgentRegistrationResponse.from_dict(response_data)
            success = response_obj.status == ResponseStatus.SUCCESS
            message = response_obj.message

            if success:
                logger.info(f"Agent {self.agent_name} successfully registered with broker")
                self.is_registered = True
                return True
            else:
                logger.error(f"Registration failed: {message}")
                return False
                
        except Exception as e:
            logger.error(f"Error during registration: {e}")
            return False
    
    def setup_rabbitmq_queue(self) -> bool:
        """Set up the RabbitMQ queue for this agent."""
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
            
            logger.info(f"RabbitMQ queue {self.queue_name} set up successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to set up RabbitMQ queue: {e}")
            return False
    
    def process_rabbitmq_message(self, ch, method, properties, body):
        """Process a message received from RabbitMQ."""
        try:
            # Parse the message
            message_dict = json.loads(body)
            
            # Try to convert to ChatMessage if it's a text or reply message
            if message_dict.get("message_type") in [MessageType.TEXT, MessageType.REPLY]:
                message = ChatMessage.from_dict(message_dict)
                logger.info(f"Received message: {message.message_id}")
            else:
                message = message_dict
                logger.info(f"Received message: {message.get('message_id', 'unknown')}")

            
            # Process the message based on its type
            asyncio.run(self.handle_message(message))
            
            # Acknowledge the message
            ch.basic_ack(delivery_tag=method.delivery_tag)
            
        except json.JSONDecodeError:
            logger.error("Received invalid JSON")
            # Reject the message
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            # Requeue the message for later processing
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
    
    async def handle_message(self, message) -> None:
        """Process a message and send a response through WebSocket."""
        try:
            # Generate a response based on the received message
            response = self.generate_response(message)
            
            # Send the response back via WebSocket
            if self.websocket:

                await self.websocket.send(json.dumps(response.to_dict()))

                # Log the response
                logger.info(f"Response sent for message {message.message_id}")

            else:
                logger.error("WebSocket connection lost, cannot send response")
                
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    def generate_response(self, message) -> Any:
        """Generate a response for a received message."""
        # Default implementation - create a simple response
        # In a real application, this method would contain agent-specific logic
        

        if isinstance(message, ChatMessage):
            # Create a reply to the received message
            text_payload = f"Agent {self.agent_name} received your message: {message.text_payload}"
            return create_reply_message(message, self.agent_id, text_payload)
        else:
            # Handle dictionary messages
            msg_dict = message if isinstance(message, dict) else {"text_payload": str(message)}
            text_payload = f"Agent {self.agent_name} received your message: {msg_dict.get('text_payload', '')}"
            
            return create_text_message(
                sender_id=self.agent_id,
                receiver_id=msg_dict.get("sender_id", "unknown"),
                text_payload=text_payload,
                in_reply_to_message_id=msg_dict.get("message_id")
            )

        
    async def listen_websocket(self) -> None:
        """Listen for control messages from the WebSocket server."""
        if not self.websocket:
            logger.error("Cannot listen: WebSocket connection not established")
            return
            
        try:
            async for message in self.websocket:
                data = json.loads(message)
                message_type = data.get("message_type")
                
                if message_type == MessageType.PING:
                    # Respond to ping with a pong, with more details to help server track status
                    server_ping_time = data.get("timestamp", "unknown")
                    response_time = datetime.now().strftime("%H:%M:%S")
                    logger.info(f"Received PING from server at {response_time}, responding with PONG")
                    
                    await self.websocket.send(json.dumps({
                        "message_type": MessageType.PONG,
                        "agent_id": self.agent_id,
                        "agent_name": self.agent_name,
                        "response_time": response_time,
                        "server_ping_time": server_ping_time
                    }))
                elif message_type == MessageType.SHUTDOWN:
                    # Handle shutdown request
                    logger.info("Received shutdown request from broker")
                    self.running = False
                    break
                elif message_type == MessageType.AGENT_STATUS_UPDATE:
                    # Agents should ignore these updates as they're meant for frontend clients
                    logger.debug("Received agent status update, ignoring as it's meant for frontend clients")
                elif message_type == MessageType.REGISTER_AGENT_RESPONSE:
                    # Handle registration response
                    if data.get("status") == ResponseStatus.SUCCESS:
                        logger.info(f"Successfully registered with broker: {data.get('message')}")
                        self.is_registered = True
                    else:
                        logger.error(f"Failed to register with broker: {data.get('message')}")
                else:
                    # Process user message
                    logger.info(f"Received message of type {message_type}")
                    
                    # If this is a chat message, process it
                    if message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
                        # Process in a separate task to avoid blocking the websocket listener
                        asyncio.create_task(self.process_message(data))
                    
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"WebSocket connection closed: {e}. Attempting to reconnect...")
            # Set flag to indicate we're no longer connected but don't stop running
            self.is_registered = False
            
            # Try to reconnect
            for attempt in range(5):
                logger.info(f"Reconnection attempt {attempt + 1}/5")
                try:
                    if await self.connect_websocket():
                        if await self.register_with_broker():
                            logger.info("Successfully reconnected and re-registered with broker")
                            # Resume listening
                            return await self.listen_websocket()
                except Exception as reconnect_error:
                    logger.error(f"Reconnection attempt failed: {reconnect_error}")
                
                # Wait before next attempt
                await asyncio.sleep(5)
            
            # If we get here, reconnection failed
            logger.error("Failed to reconnect after multiple attempts. Shutting down.")
            self.running = False
            
        except Exception as e:
            logger.error(f"Error in WebSocket listener: {e}")
            self.running = False
    
    def start_rabbitmq_consumer(self) -> None:
        """Start consuming messages from RabbitMQ queue."""
        if not self.rabbitmq_channel:
            logger.error("Cannot start consumer: RabbitMQ connection not established")
            return
            
        try:
            logger.info(f"Starting to consume messages from queue {self.queue_name}")
            self.rabbitmq_channel.start_consuming()
        except Exception as e:
            logger.error(f"Error in RabbitMQ consumer: {e}")
    
    async def run(self) -> None:
        """Run the agent's main loop."""
        self.running = True
        
        # Connect to WebSocket
        if not await self.connect_websocket():
            logger.error("Failed to connect to WebSocket server. Exiting.")
            return
        
        # Register with broker
        if not await self.register_with_broker():
            logger.error("Failed to register with broker. Exiting.")
            return
        
        # Connect to RabbitMQ
        if not self.connect_rabbitmq():
            logger.error("Failed to connect to RabbitMQ. Exiting.")
            return
        
        # Set up RabbitMQ queue
        if not self.setup_rabbitmq_queue():
            logger.error("Failed to set up RabbitMQ queue. Exiting.")
            return
        
        # Start RabbitMQ consumer in a separate thread
        import threading
        consumer_thread = threading.Thread(target=self.start_rabbitmq_consumer)
        consumer_thread.daemon = True
        consumer_thread.start()
        
        # Listen for control messages on WebSocket
        try:
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

    async def process_message(self, message_data):
        """Process an incoming chat message."""
        try:
            # Extract message details
            message_type = message_data.get("message_type")
            sender_id = message_data.get("sender_id", "unknown")
            text_payload = message_data.get("text_payload", "")
            
            logger.info(f"Processing message from {sender_id}: {text_payload[:50]}...")
            
            # Generate a simple echo response for now
            # This is where you would add your agent's specific logic
            response_text = f"Echo: {text_payload}"
            
            # Create a response message
            response = {
                "message_type": MessageType.REPLY,
                "sender_id": self.agent_id,
                "receiver_id": sender_id,  # Reply to the sender
                "text_payload": response_text
            }
            
            # Send the response
            if self.websocket and self.websocket.open:
                await self.websocket.send(json.dumps(response))
                logger.info(f"Sent response to {sender_id}")
            else:
                logger.error("Cannot send response: WebSocket connection not open")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            
            # Try to send an error message back if possible
            if self.websocket and self.websocket.open:
                error_response = {
                    "message_type": MessageType.ERROR,
                    "sender_id": self.agent_id,
                    "receiver_id": message_data.get("sender_id", "unknown"),
                    "text_payload": f"Error processing your message: {str(e)}"
                }
                await self.websocket.send(json.dumps(error_response))
                logger.info(f"Sent error response to {message_data.get('sender_id', 'unknown')}")

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run an agent that connects to a broker via WebSocket and processes messages from RabbitMQ")
    
    parser.add_argument("--id", type=str, help="Unique identifier for this agent")
    parser.add_argument("--name", type=str, required=True, help="Human-readable name for this agent")
    parser.add_argument("--ws-url", type=str, default="ws://localhost:8765/ws", help="WebSocket server URL")
    parser.add_argument("--rabbitmq-host", type=str, default="localhost", help="RabbitMQ server host")
    
    return parser.parse_args()

async def main():
    """Main entry point for the agent."""
    # Parse command line arguments
    args = parse_arguments()
    
    # Generate a unique ID if not provided
    agent_id = args.id if args.id else f"agent_{uuid.uuid4().hex[:8]}"
    
    # Create and run the agent
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
            # Force exit to terminate all running threads
            agent.cleanup()
            # Cancel all running tasks
            for task in asyncio.all_tasks(loop):
                if task is not asyncio.current_task():
                    task.cancel()
            loop.stop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        logger.info(f"Starting agent {agent.agent_name} (ID: {agent.agent_id})")
        await agent.run()
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
    finally:
        logger.info("Agent shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
