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
