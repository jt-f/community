import pika
import argparse
import asyncio
import json
import logging
import os
import signal
import uuid
from datetime import datetime
import time
from mistralai import Mistral

from shared_models import (
    MessageType,
    setup_logging
)

# Import agent configuration and gRPC client
import config as agent_config
import grpc_client

# Import new modules
from agent_init import register_with_server, connect_rabbitmq, setup_rabbitmq_queue, start_rabbitmq_consumer
from messaging import publish_to_broker_input_queue, process_rabbitmq_message

# Configure logging
logger = setup_logging(__name__)

# Reduce verbosity from pika library
logging.getLogger("pika").setLevel(logging.WARNING)
logger.info("Pika library logging level set to WARNING.")

class Agent:
    def __init__(self, agent_id: str, agent_name: str, rabbitmq_host: str):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.rabbitmq_host = rabbitmq_host
        self.rabbitmq_port = int(os.getenv("RABBITMQ_PORT", "5672"))
        self.rabbitmq_connection = None
        self.rabbitmq_channel = None
        self.queue_name = f"agent_queue_{self.agent_id}"
        self.is_registered = False
        self.running = False
        self.paused = False  # Add a paused state flag
        
        # Initialize Mistral Client
        self.mistral_client = None
        self.mistral_model = agent_config.MISTRAL_MODEL
        logger.info(f"agent config key: {agent_config.MISTRAL_API_KEY}")
        logger.info(f"agent config model: {agent_config.MISTRAL_MODEL}")
        if agent_config.MISTRAL_API_KEY:
            try:
                self.mistral_client = Mistral(api_key=agent_config.MISTRAL_API_KEY)
                logger.info("Mistral client initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize Mistral client: {e}")
        else:
            logger.warning("Mistral API key not found, LLM features disabled.")
        
    def connect_rabbitmq(self) -> bool:
        """Connect to RabbitMQ server for message processing using registration module."""
        connection, channel = connect_rabbitmq(self.rabbitmq_host, self.rabbitmq_port, logger)
        if connection and channel:
            self.rabbitmq_connection = connection
            self.rabbitmq_channel = channel
            return True
        return False

    async def register_with_server(self) -> bool:
        """Register the agent with the server via gRPC."""
        # Get server host and port from environment or use defaults
        server_host = os.getenv("GRPC_HOST", "localhost")
        server_port = int(os.getenv("GRPC_PORT", "50051"))
        
        # Send registration via gRPC with server host and port first
        result = await grpc_client.register_agent(
            server_host=server_host,
            server_port=server_port,
            name=self.agent_name,
            custom_id=self.agent_id
        )
        self.is_registered = result
        return result
    
    def setup_rabbitmq_queue(self) -> bool:
        """Set up the RabbitMQ queue for receiving messages using registration module."""
        if not self.rabbitmq_channel:
            logger.error("Cannot setup queue: RabbitMQ channel not established")
            return False
        return setup_rabbitmq_queue(self.rabbitmq_channel, self.queue_name, self.process_rabbitmq_message, logger)
    
    def publish_to_broker_input_queue(self, message_data: dict) -> bool:
        return publish_to_broker_input_queue(self.rabbitmq_channel, message_data)
    
    def process_rabbitmq_message(self, ch, method, properties, body):
        return process_rabbitmq_message(self, ch, method, properties, body)
    
    def start_rabbitmq_consumer(self) -> None:
        return start_rabbitmq_consumer(self)
    
    def generate_response(self, message: dict) -> dict:
        """Generate a response for a received message using Mistral LLM."""
        from processing import generate_response
        return generate_response(self, message)

    async def run(self) -> None: # Keep async for gRPC registration
        """Run the agent's main loop (gRPC for registration, RabbitMQ for messages)."""
        self.running = True
        
        # Register with server first (uses gRPC)
        if not await self.register_with_server():
            logger.error("Failed to register with server. Exiting.")
            return
            
        # Update status to online after successful registration
        await self.update_status("online")
        
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
        
        # Keep the main async loop running while the consumer thread operates
        # This allows signal handling and potential future async tasks
        try:
            while self.running:
                # Yield control to allow other async tasks (like signal handlers)
                await asyncio.sleep(1) 
        except asyncio.CancelledError:
             logger.info("Main agent loop cancelled.")
        finally:
            logger.info("Main agent loop finished. Initiating cleanup.")
            self.cleanup()
    
    def cleanup(self) -> None:
        """Clean up connections before exit."""
        logger.info("Cleaning up before exit...")
        
        # Update status to offline before cleanup
        asyncio.run(self.update_status("offline"))
        
        # Close RabbitMQ connection
        if self.rabbitmq_connection and self.rabbitmq_connection.is_open:
            try:
                if self.rabbitmq_channel and self.rabbitmq_channel.is_open:
                    if hasattr(self.rabbitmq_channel, 'consumer_tags') and self.rabbitmq_channel.consumer_tags:
                         self.rabbitmq_channel.stop_consuming()
                self.rabbitmq_connection.close()
                logger.info("RabbitMQ connection closed")
            except Exception as e:
                logger.error(f"Error closing RabbitMQ connection: {e}")
                
    def pause(self) -> bool:
        """Pause the agent's message processing by stopping queue consumption."""
        if self.paused:
            logger.info("Agent is already paused")
            return False
            
        logger.info(f"Pausing agent {self.agent_name} ({self.agent_id})")
        
        # Set paused flag FIRST to ensure consumer thread doesn't try to process messages
        self.paused = True
        
        # Now that consumer thread is skipping process_data_events, we can safely cancel consumers
        pause_success = True
        if self.rabbitmq_channel and self.rabbitmq_channel.is_open:
            try:
                # Get consumer tags safely
                consumer_tags = []
                if hasattr(self.rabbitmq_channel, 'consumer_tags'):
                    try:
                        consumer_tags = list(self.rabbitmq_channel.consumer_tags)
                    except Exception as e:
                        logger.warning(f"Error getting consumer tags: {e}")
                        consumer_tags = []
                
                # Store consumer tags for later resume
                self.saved_consumer_tags = consumer_tags
                
                # Cancel consumers if we have any
                if consumer_tags:
                    for tag in consumer_tags:
                        try:
                            self.rabbitmq_channel.basic_cancel(consumer_tag=tag)
                            logger.info(f"Cancelled consumer {tag}")
                        except Exception as e:
                            logger.error(f"Error cancelling consumer {tag}: {e}")
                            pause_success = False
                else:
                    logger.info("No active consumers to cancel")
                
                if pause_success:
                    logger.info(f"Stopped consuming from queue {self.queue_name}")
            except Exception as e:
                logger.error(f"Error stopping queue consumption: {e}")
                pause_success = False
        else:
            logger.error("Cannot pause: RabbitMQ channel is not open or available.")
            pause_success = False
        
        if pause_success:
            logger.info(f"Agent {self.agent_name} ({self.agent_id}) is now paused")
            # Send status update to server immediately
            asyncio.run(self.update_status("paused"))
            return True
        else:
            # If we failed to properly pause, reset the paused flag
            self.paused = False
            logger.error(f"Failed to pause agent {self.agent_name} ({self.agent_id})")
            return False
        
    def resume(self) -> bool:
        """Resume the agent's message processing by restarting queue consumption."""
        # Don't check paused state here - we want to allow resuming even if we think we're not paused
        # This helps handle cases where our state is out of sync with the server
            
        logger.info(f"Resuming agent {self.agent_name} ({self.agent_id})")
        
        # First check if we need to reconnect to RabbitMQ
        if not self.rabbitmq_channel or not self.rabbitmq_channel.is_open:
            logger.info("RabbitMQ channel not available, attempting to reconnect...")
            if not self.connect_rabbitmq():
                logger.error("Failed to reconnect to RabbitMQ")
                return False
            if not self.setup_rabbitmq_queue():
                logger.error("Failed to setup RabbitMQ queue after reconnection")
                return False
        
        # First restart consuming from the queue before changing paused state
        resume_success = True
        if self.rabbitmq_channel and self.rabbitmq_channel.is_open:
            try:
                # Re-setup the queue with our callback
                from messaging import process_rabbitmq_message
                
                # Setup the queue with our callback
                self.rabbitmq_channel.queue_declare(queue=self.queue_name, durable=True)
                self.rabbitmq_channel.basic_consume(
                    queue=self.queue_name,
                    on_message_callback=lambda ch, method, properties, body: process_rabbitmq_message(self, ch, method, properties, body),
                    auto_ack=False
                )
                logger.info(f"Resumed consuming from queue {self.queue_name}")
            except Exception as e:
                logger.error(f"Error resuming queue consumption: {e}")
                resume_success = False
        else:
            logger.error("Cannot resume: RabbitMQ channel is not open or available.")
            resume_success = False
        
        # Only change paused state if we successfully resumed consumption
        if resume_success:
            # Finally, clear the paused flag
            self.paused = False
            logger.info(f"Agent {self.agent_name} ({self.agent_id}) is now resumed")
            # Send status update to server immediately
            asyncio.run(self.update_status("online"))
            return True
        else:
            logger.error(f"Failed to resume agent {self.agent_name} ({self.agent_id})")
            return False
        
    def get_status(self) -> dict:
        """Get the current status of the agent."""
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "is_registered": self.is_registered,
            "running": self.running,
            "paused": self.paused
        }

    async def update_status(self, status: str) -> bool:
        """Update the agent's status on the server.
        
        Args:
            status: The new status (e.g., 'online', 'paused', 'offline')
            
        Returns:
            bool: True if the status was updated successfully, False otherwise
        """
        if not self.is_registered:
            logger.warning("Cannot update status: Agent is not registered")
            return False
            
        try:
            server_host = os.getenv("GRPC_HOST", "localhost")
            server_port = int(os.getenv("GRPC_PORT", "50051"))
            return await grpc_client.send_status_update(server_host, server_port, status)
        except Exception as e:
            logger.error(f"Error updating agent status: {e}")
            return False

# Create a global reference to the agent instance
current_agent = None

def agent_command_callback(command):
    global current_agent
    logger.info(f"Received command from server: {command}")
    
    # Default response is success
    result = {
        "success": True,
        "output": "Command acknowledged",
        "error_message": "",
        "exit_code": 0
    }
    
    command_type = command.get("type", "")
    
    if command_type == "pause":
        logger.info(f"Received PAUSE command (id={command.get('command_id')}) from server.")
        if current_agent:
            if current_agent.pause():
                result["output"] = f"Agent {current_agent.agent_name} paused successfully"
            else:
                result["output"] = f"Agent {current_agent.agent_name} is already paused"
        else:
            result["success"] = False
            result["error_message"] = "No agent instance available to pause"
            result["exit_code"] = 1
    
    elif command_type == "resume" or command_type == "unpause":
        logger.info(f"Received {command_type.upper()} command (id={command.get('command_id')}) from server.")
        if current_agent:
            if current_agent.resume():
                result["output"] = f"Agent {current_agent.agent_name} resumed successfully"
            else:
                result["output"] = f"Agent {current_agent.agent_name} is not paused"
        else:
            result["success"] = False
            result["error_message"] = f"No agent instance available to {command_type}"
            result["exit_code"] = 1
    
    elif command_type == "status":
        logger.info(f"Received STATUS command (id={command.get('command_id')}) from server.")
        if current_agent:
            status = current_agent.get_status()
            result["output"] = f"Agent status: {json.dumps(status)}"
        else:
            result["success"] = False
            result["error_message"] = "No agent instance available to get status"
            result["exit_code"] = 1
    
    else:
        logger.warning(f"Received unknown command type: {command_type}")
        result["success"] = False
        result["output"] = f"Unknown command type: {command_type}"
        result["error_message"] = f"Command type {command_type} not supported"
        result["exit_code"] = 1
    
    return result

# Register the callback with the gRPC client
grpc_client.set_command_callback(agent_command_callback)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run an agent using gRPC and RabbitMQ")
    
    parser.add_argument("--id", type=str, help="Unique identifier for this agent")
    parser.add_argument("--name", type=str, required=True, help="Human-readable name for this agent")
    parser.add_argument("--rabbitmq-host", type=str, default=os.getenv("RABBITMQ_HOST", "localhost"), 
                       help="RabbitMQ server host for message processing")
    
    return parser.parse_args()

async def main():
    """Main entry point for the agent using the hybrid approach."""
    global current_agent
    
    # Parse command line arguments
    args = parse_arguments()
    
    # Generate a unique ID if not provided
    agent_id = args.id if args.id else f"agent_{uuid.uuid4().hex[:8]}"
    
    # Create and run the agent with the hybrid approach
    agent = Agent(
        agent_id=agent_id,
        agent_name=args.name,
        rabbitmq_host=args.rabbitmq_host
    )
    
    # Set the global reference to the agent instance
    current_agent = agent
    
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
        logger.info(f"Starting agent {agent.agent_name} (ID: {agent.agent_id}) with gRPC and RabbitMQ communication")
        logger.info(f"- RabbitMQ queues for message processing")
        await agent.run()
    except asyncio.CancelledError:
        logger.info("Agent run cancelled.")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
    finally:
        logger.info("Agent shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
