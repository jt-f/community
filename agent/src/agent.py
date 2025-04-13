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

# Configure logging
logger = setup_logging(__name__)

# Reduce verbosity from pika library
logging.getLogger("pika").setLevel(logging.WARNING)
logger.info("Pika library logging level set to WARNING.")

# Define the server input queue name (should match server config)
# SERVER_INPUT_QUEUE = "server_input_queue" # Not directly used by agent, defined in publish func

class Agent:
    def __init__(self, agent_id: str, agent_name: str, rabbitmq_host: str):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.rabbitmq_host = rabbitmq_host
        self.rabbitmq_connection = None
        self.rabbitmq_channel = None
        self.queue_name = f"agent_queue_{self.agent_id}"
        self.is_registered = False
        self.running = False
        
        # Initialize Mistral Client
        self.mistral_client = None
        logger.info(f"agent config key: {agent_config.MISTRAL_API_KEY}")
        logger.info(f"agent config model: {agent_config.MISTRAL_MODEL}")
        # Initialize Mistral Client
        if agent_config.MISTRAL_API_KEY:
            try:
                self.mistral_client = Mistral(api_key=agent_config.MISTRAL_API_KEY)
                logger.info("Mistral client initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize Mistral client: {e}")
        else:
            logger.warning("Mistral API key not found, LLM features disabled.")
        
    def connect_rabbitmq(self) -> bool:
        """Connect to RabbitMQ server for message processing."""
        try:
            if self.rabbitmq_connection and self.rabbitmq_connection.is_open:
                logger.info("RabbitMQ connection already established")
                return True
                
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
        """Register the agent with the server via gRPC."""
        try:
            # Get server host and port from environment or use defaults
            server_host = os.getenv("GRPC_HOST", "localhost")
            server_port = int(os.getenv("GRPC_PORT", "50051"))
            
            # Send registration via gRPC
            response = await grpc_client.register_agent(
                server_host=server_host,
                server_port=server_port,
                name=self.agent_name,
                custom_id=self.agent_id
            )
            
            if response:
                logger.info(f"Agent registered successfully with ID: {self.agent_id}")
                self.is_registered = True
                return True
            else:
                logger.error("Registration failed")
                return False
                
        except Exception as e:
            logger.error(f"Error during registration: {e}")
            return False
    
    def setup_rabbitmq_queue(self) -> bool:
        """Set up the RabbitMQ queue for receiving messages."""
        if not self.rabbitmq_connection or not self.rabbitmq_connection.is_open:
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
            # Add a routing status to indicate this message is pending broker routing
            message_data["routing_status"] = "pending"
            
            # Ensure the queue exists (optional, server should declare it)
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

            logger.info(f"Published response message {message_data.get('message_id', 'N/A')} to broker_input_queue")
            return True
        except Exception as e:
            logger.error(f"Failed to publish to broker_input_queue: {e}")
            return False
    
    def process_rabbitmq_message(self, ch, method, properties, body):
        """Process a message received from RabbitMQ queue."""
        try:
            # Parse the message
            message_dict = json.loads(body)
            logger.info(f"Received message: {message_dict}")
            # Log the received message
            message_type = message_dict.get("message_type", "unknown")
            message_id = message_dict.get("message_id", "unknown")
            sender_id = message_dict.get("sender_id", "unknown")
            if message_type == MessageType.SERVER_HEARTBEAT:
                logger.debug(f"Received heartbeat from server")
            else:
                logger.info(f"Received message type={message_type}, id={message_id} from {sender_id} via queue")
                logger.info(f"Message: {message_dict}")
            
            # Introduce a delay
            delay = 5
            logger.info(f"Waiting {delay} seconds before processing...")
            time.sleep(delay)
            logger.info("Finished waiting, proceeding with processing.")
            
            # Process the message and generate response
            response = self.generate_response(message_dict)
            logger.info(f"Generated response: {response.get('text_payload','ERROR: NO TEXT PAYLOAD')}")
            # Send response back through broker_input_queue
            if self.publish_to_broker_input_queue(response):
                logger.info(f"Sent response {response.get('message_id','ERROR: NO MESSAGE ID')} to message {message_id} to broker_input_queue")
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
    
    def generate_response(self, message: dict) -> dict:
        """Generate a response for a received message using Mistral LLM."""
        sender_id = message.get("sender_id", "unknown")
        text_payload = message.get("text_payload", "")
        message_id = message.get("message_id", None)
        llm_response_text = "Sorry, I cannot generate a response right now." # Default response
        
        message_type = MessageType.REPLY
        if self.mistral_client and text_payload:
            logger.info(f"Sending text to Mistral model {agent_config.MISTRAL_MODEL}...")
            try:
                chat_response = self.mistral_client.chat.complete(
                    model = agent_config.MISTRAL_MODEL,
                    messages = [
                        {
                            "role": "user",
                            "content": text_payload,
                        },
                    ]
                )

                logger.info(f'Mistral response: {chat_response.choices[0].message.content}')
                llm_response_text = chat_response.choices[0].message.content
            except Exception as e:
                logger.error(f"Error generating with Mistral: {str(e)}")
                return {"error": str(e)}
            
        elif not self.mistral_client:
            message_type = MessageType.ERROR
            logger.warning("Mistral client not available. Cannot generate LLM response.")
            llm_response_text = "LLM client is not configured." # Config specific response

        # Create a response dictionary
        response = {
            "message_type": message_type,
            "sender_id": self.agent_id,
            "receiver_id": sender_id,
            "text_payload": llm_response_text,
            "timestamp": datetime.now().isoformat(),
            "message_id": f"msg_{uuid.uuid4().hex}" # Add a unique ID for this reply message
        }

        logger.info(f"Generated response: {response['text_payload']}")

        # Add reference to original message if available
        if message_id:
            response["in_reply_to_message_id"] = message_id # Use the correct key
            
        return response

    def start_rabbitmq_consumer(self) -> None:
        """Start consuming messages from the RabbitMQ queue."""
        if not self.rabbitmq_connection or not self.rabbitmq_connection.is_open:
            logger.error("Cannot start consumer: RabbitMQ connection not established")
            return
            
        try:
            logger.info(f"Starting to consume messages from queue {self.queue_name}")
            while self.running:
                try:
                    self.rabbitmq_connection.process_data_events(time_limit=1)
                except pika.exceptions.ConnectionClosedByBroker:
                    logger.warning("RabbitMQ connection closed by broker. Attempting to reconnect...")
                    if not self.connect_rabbitmq() or not self.setup_rabbitmq_queue():
                        logger.error("Failed to reconnect to RabbitMQ. Exiting consumer thread.")
                        break
                except pika.exceptions.AMQPConnectionError:
                    logger.warning("RabbitMQ connection error. Attempting to reconnect...")
                    if not self.connect_rabbitmq() or not self.setup_rabbitmq_queue():
                        logger.error("Failed to reconnect to RabbitMQ. Exiting consumer thread.")
                        break
                except Exception as e:
                    logger.error(f"Error in RabbitMQ consumer: {e}")
                    time.sleep(1)  # Wait before retrying
        except Exception as e:
            logger.error(f"Error in RabbitMQ consumer: {e}")
        finally:
            self.cleanup()
    
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
