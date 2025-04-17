import logging
import threading
import json
import time
import pika
import os
import random
from datetime import datetime
from typing import Dict
import asyncio
import signal
from shared_models import setup_logging, MessageType, ResponseStatus
import grpc_client

logger = setup_logging(__name__)

# Define the broker name/ID
BROKER_ID = f"broker_{random.randint(1000, 9999)}"

# Reduce verbosity from pika library
logging.getLogger("pika").setLevel(logging.WARNING)
logger.info("Pika library logging level set to WARNING.")

# Connection details
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
BROKER_INPUT_QUEUE = "broker_input_queue"         
AGENT_METADATA_QUEUE = "agent_metadata_queue"
SERVER_INPUT_QUEUE = "server_input_queue"
SERVER_ADVERTISEMENT_QUEUE = "server_advertisement_queue"

# Dictionary to store registered agents - the only state the broker needs
registered_agents = {}  # agent_id -> agent info (capabilities, name, etc.)

# Global flag for shutdown coordination
shutdown_event = asyncio.Event()

# --- RabbitMQ Setup and Management ---
def setup_rabbitmq_channel(queue_name, callback_function):
    """Set up a RabbitMQ channel and consumer."""
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT))
        channel = connection.channel()
        
        # Declare the queue, ensuring it exists
        channel.queue_declare(queue=queue_name, durable=True)
        
        # Set up the consumer
        channel.basic_consume(
            queue=queue_name,
            on_message_callback=lambda ch, method, properties, body: callback_function(ch, method, properties, body),
            auto_ack=False
        )
        
        logger.info(f"Connected to RabbitMQ and consuming from {queue_name}")
        return channel
    except Exception as e:
        logger.error(f"Failed to set up RabbitMQ channel for {queue_name}: {e}")
        return None

def publish_to_server_input_queue(message_data: dict) -> bool:
    """Publish a message to the server's input queue."""
    try:
        # Re-establish connection for each publish for simplicity
        # In high-throughput scenarios, consider a persistent connection/channel
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT))
        channel = connection.channel()

        # Ensure the queue exists (server should primarily declare it)
        channel.queue_declare(queue=SERVER_INPUT_QUEUE, durable=True)

        # Publish the message
        logger.info(f"Publishing message to {SERVER_INPUT_QUEUE}: {message_data}")
        channel.basic_publish(
            exchange='',
            routing_key=SERVER_INPUT_QUEUE,
            body=json.dumps(message_data),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            )
        )

        logger.debug(f"Published message {message_data.get('message_id', 'N/A')} to {SERVER_INPUT_QUEUE}")

        # Clean up
        connection.close()
        return True
    except Exception as e:
        logger.error(f"Failed to publish to {SERVER_INPUT_QUEUE}: {e}")
        return False

# --- Message Handling ---
def handle_incoming_message(channel, method, properties, body):
    """Handle incoming chat messages from the BROKER_INPUT_QUEUE."""
    try:
        message_data = json.loads(body)
        message_type = message_data.get("message_type")
        sender_id = message_data.get("sender_id", "unknown")
        receiver_id = message_data.get("receiver_id")
        routing_status = message_data.get("routing_status", "unknown")
        
        if message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
            logger.info(f"Incoming {message_type} message {message_data.get('message_id','N/A')} from {sender_id} : '{message_data.get('text_payload','N/A')}' (routing_status={routing_status})")
            
            # Request agent status update before routing
            logger.info("Requesting agent status update before routing message")
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Run the async function in the new event loop
                loop.run_until_complete(request_agent_status_via_grpc())
            finally:
                loop.close()
            
            # If a message already has a specific receiver_id and isn't an error,
            # we can forward it directly without routing
            if receiver_id and routing_status != "error" and receiver_id in registered_agents:
                logger.info(f"Message already has valid receiver_id ({receiver_id}), forwarding directly.")
                # Make sure to set the routing status to routed
                message_data["routing_status"] = "routed"
                publish_to_server_input_queue(message_data)
            else:
                # Otherwise route the message
                route_message(message_data)
                
            # Acknowledge the message was processed
            channel.basic_ack(delivery_tag=method.delivery_tag)
        elif message_type == MessageType.AGENT_STATUS_UPDATE:
            # This shouldn't typically arrive here, but handle defensively
            logger.debug(f"Received AGENT_STATUS_UPDATE from {sender_id} in input queue (unexpected)")
            handle_agent_status_update(message_data)
            channel.basic_ack(delivery_tag=method.delivery_tag)
        elif message_type == MessageType.ERROR:
            logger.warning(f"Received ERROR message from {sender_id}. Forwarding to server.")
            # Forward error messages directly to the server via the server input queue
            if "routing_status" not in message_data:
                message_data["routing_status"] = "error"
            publish_to_server_input_queue(message_data)
            channel.basic_ack(delivery_tag=method.delivery_tag)
        else:
            logger.warning(f"Received unsupported message type in broker input queue: {message_type} from {sender_id}")
            # Acknowledge but skip processing
            channel.basic_ack(delivery_tag=method.delivery_tag)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in message: {body}")
        # Acknowledge but don't process invalid messages
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error(f"Error processing incoming message: {e}")
        # Negative acknowledgment for failed processing
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

# --- Agent Status Management ---
def handle_agent_status_update(message_data):
    """Process agent status updates received via gRPC."""
    logger.info(f"Processing agent status update: {message_data}")
    
    if message_data.get("message_type") != MessageType.AGENT_STATUS_UPDATE:
        logger.warning(f"Received non-status update message in status handler: {message_data.get('message_type')}")
        return
    
    agents_data = message_data.get("agents", [])
    is_full_update = message_data.get("is_full_update", False)
    
    # --- Handle empty agent list explicitly ---
    if not agents_data:
        logger.warning("Received empty agent status update. Treating as NO agents registered/online.")
        registered_agents.clear()
        logger.info(f"Cleared registered agents list due to empty update.")
        # Log the final state after processing
        online_agents = [agent_id for agent_id, info in registered_agents.items() if info.get("is_online", False)]
        logger.info(f"After empty status update: Total agents: {len(registered_agents)}, Online agents: {len(online_agents)}")
        return # Stop processing here
        
    logger.info(f"Processing status update for {len(agents_data)} agents (is_full_update={is_full_update})")
    
    # If this is a full update, we could optionally clear our previous state
    if is_full_update:
        logger.info("This is a full update - clearing previous agent state before processing")
        registered_agents.clear()
    
    updated_ids = set()
    # Update our internal state with the current agent statuses
    for agent in agents_data:
        agent_id = agent.get("agent_id")
        if not agent_id:
            logger.warning("Received agent status entry with no ID")
            continue
        
        updated_ids.add(agent_id)
        is_online = agent.get("is_online", False)
        agent_name = agent.get("agent_name", "Unknown Agent")
        
        # If this is a new agent we haven't seen before or updating existing
        if agent_id not in registered_agents:
            registered_agents[agent_id] = {
                "name": agent_name,
                "registration_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "is_online": is_online
            }
            logger.info(f"Added new agent from status update: {agent_name} ({agent_id}), Online: {is_online}")
        else:
            # Update existing agent's online status if it changed
            if registered_agents[agent_id].get("is_online") != is_online:
                old_status = registered_agents[agent_id].get("is_online")
                registered_agents[agent_id]["is_online"] = is_online
                logger.info(f"Updated agent status: {agent_name} ({agent_id}), Online status changed: {old_status} -> {is_online}")
            # Optionally update name if it changed
            if registered_agents[agent_id].get("name") != agent_name:
                old_name = registered_agents[agent_id].get("name")
                registered_agents[agent_id]["name"] = agent_name
                logger.info(f"Updated agent name: {agent_id} from '{old_name}' to '{agent_name}'")
    
    # If it was a full update, mark any agents not in the update as offline
    if is_full_update:
        logger.info("Processing full status update - marking missing agents as offline")
        agents_to_mark_offline = set(registered_agents.keys()) - updated_ids
        for agent_id in agents_to_mark_offline:
            if registered_agents[agent_id].get("is_online", False):
                registered_agents[agent_id]["is_online"] = False
                logger.info(f"Marked agent {registered_agents[agent_id].get('name', agent_id)} ({agent_id}) as offline (not in full update)")
    
    # Log the final state after processing
    online_agents = [agent_id for agent_id, info in registered_agents.items() if info.get("is_online", False)]
    logger.info(f"After status update: Total agents: {len(registered_agents)}, Online agents: {len(online_agents)}")
    logger.info(f"Online agents: {online_agents}")
    logger.info(f"Registered agents: {registered_agents}")

# Create a new async version of handle_agent_status_update for gRPC
async def handle_agent_status_update_async(message_data):
    """Async wrapper for handle_agent_status_update to be used with gRPC."""
    handle_agent_status_update(message_data)

# --- Message Routing ---
def route_message(message_data):
    """Route messages to the appropriate recipients.
    If receiver_id is 'broadcast' or not specified, randomly selects an online agent.
    Otherwise, attempts direct routing to the specified agent.
    
    Never routes a message back to the agent who sent it.
    All messages are published to BROKER_OUTPUT_QUEUE with appropriate receiver_id set.
    """
    message_type = message_data.get("message_type")
    sender_id = message_data.get("sender_id", "unknown")
    message_id = message_data.get("message_id", "N/A")
    logger.debug(f"[DEBUG] Routing message from {sender_id} type={message_type}")
    
    # If the sender looks like an agent but we don't know about it, request agent status
    if sender_id.startswith("agent_") and sender_id not in registered_agents:
        logger.warning(f"Message from unknown agent {sender_id}. Requesting agent status update.")
        asyncio.create_task(request_agent_status_via_grpc())
    
    # Create a clean copy of the message for routing
    outgoing_message = dict(message_data)
    
    # Remove any routing metadata fields that might be present
    for field in ["_broadcast", "_target_agent_id", "_client_id"]:
        if field in outgoing_message:
            outgoing_message.pop(field)
    
    # Update routing status to indicate this message has been routed by the broker
    outgoing_message["routing_status"] = "routed"

    # Extract original text payload for error messages
    original_text = message_data.get("text_payload", "")
    truncated_text = (original_text[:20] + '...') if len(original_text) > 20 else original_text

    # Thoroughly log the state of all agents
    logger.debug(f"[DEBUG] All registered agents: {json.dumps(registered_agents)}")
    
    # Log all agent statuses
    for agent_id, info in registered_agents.items():
        logger.debug(f"[DEBUG] Agent {agent_id}: name={info.get('name', 'unknown')}, is_online={info.get('is_online', False)}")
    logger.info(f"Registered agents : {registered_agents}")

    # Get list of online agents, EXCLUDING the sender if it's an agent
    online_agents = [
        agent_id for agent_id, info in registered_agents.items()
        if info.get("is_online", False) and agent_id != sender_id  # Exclude the sender
    ]

    logger.info(f"Online agents (excluding sender): {online_agents}")
    
    if online_agents:
        # Randomly select an agent (that is not the sender)
        chosen_agent_id = random.choice(online_agents)
        
        # Set the receiver_id to the chosen agent
        outgoing_message["receiver_id"] = chosen_agent_id
        
        # Send the message
        logger.info(f"Routing message {message_id} to agent {chosen_agent_id}")
        publish_to_server_input_queue(outgoing_message) # Send routed message to server queue
        return
    else:
        # Count how many total online agents we have
        all_online_agents = [
            agent_id for agent_id, info in registered_agents.items()
            if info.get("is_online", False)
        ]
        
        logger.info(f"All online agents (including sender): {all_online_agents}")
        
        error_text = ""
        # If sender is the only online agent
        if sender_id in all_online_agents and len(all_online_agents) == 1:
            # Get the agent's name for the error message
            agent_name = registered_agents.get(sender_id, {}).get("name", sender_id) # Fallback to ID if name not found
            error_text = f"Only the sending agent {agent_name} is online. Cannot route message."
            logger.warning(f"{error_text} Cannot route message '{truncated_text}' to another agent.")
        else:
            # No online agents available (other than potentially the sender)
            error_text = "No other online agents available. Routing failed."
            logger.warning(f"Could not route message '{truncated_text}' from {sender_id}: {error_text}")

        # Construct the error response to send back to the server
        error_response = {
            "message_id": message_id,
            "message_type": MessageType.ERROR,
            "sender_id": sender_id, # Original sender
            "receiver_id": "Server",     # Target the server for processing this error
            "routing_status": "error",   # Mark as routing error
            "text_payload": original_text, # <-- Include the ORIGINAL message text
            "routing_status_message": error_text # <-- Put the error DESCRIPTION here
        }
        publish_to_server_input_queue(error_response)
        return

# --- gRPC Integration ---
async def request_agent_status_via_grpc():
    """Request agent status update via gRPC.
    This is called when the broker encounters an unknown agent ID.
    """
    # Rate limiting to prevent flooding the server with requests
    if hasattr(request_agent_status_via_grpc, '_last_request_time'):
        current_time = time.time()
        if current_time - request_agent_status_via_grpc._last_request_time < 5:
            logger.debug("Skipping agent status request due to rate limiting")
            return
        request_agent_status_via_grpc._last_request_time = current_time
    else:
        request_agent_status_via_grpc._last_request_time = time.time()
    
    try:
        # Get gRPC configuration
        grpc_host = os.getenv("GRPC_HOST", "localhost")
        grpc_port = int(os.getenv("GRPC_PORT", "50051"))
        
        logger.info(f"Requesting agent status update via gRPC from {grpc_host}:{grpc_port}")
        
        # Request agent status directly via gRPC
        response = await grpc_client.request_agent_status(
            host=grpc_host,
            port=grpc_port,
            broker_id=BROKER_ID
        )
        
        logger.info(f"Received gRPC response: {response}")
        
        if not response:
            logger.error("Received None response from gRPC server")
            return
            
        # Handle both dictionary and gRPC response types
        if isinstance(response, dict):
            logger.info("Received dictionary response, converting to message format")
            message_data = {
                "message_type": MessageType.AGENT_STATUS_UPDATE,
                "agents": response.get("agents", []),
                "is_full_update": True
            }
        else:
            # Handle gRPC response object
            if not hasattr(response, 'agents'):
                logger.error(f"Invalid response format from gRPC server. Response type: {type(response)}")
                return
                
            if not response.agents:
                logger.warning("Received empty agents list from gRPC server")
                return
                
            logger.info(f"Processing {len(response.agents)} agents from gRPC response")
            
            # Convert gRPC response to message format
            message_data = {
                "message_type": MessageType.AGENT_STATUS_UPDATE,
                "agents": [
                    {
                        "agent_id": agent.agent_id,
                        "agent_name": agent.agent_name,
                        "is_online": agent.is_online
                    }
                    for agent in response.agents
                ],
                "is_full_update": True
            }
        
        # Process the update
        handle_agent_status_update(message_data)
            
    except Exception as e:
        logger.error(f"Error requesting agent status via gRPC: {e}")
        logger.exception("Full traceback for gRPC error:")

async def register_broker_via_grpc():
    """Register the broker with the server using gRPC."""
    try:
        # Get gRPC configuration
        grpc_host = os.getenv("GRPC_HOST", "localhost")
        grpc_port = int(os.getenv("GRPC_PORT", "50051"))
        
        logger.info(f"Registering broker via gRPC with {grpc_host}:{grpc_port}")
        
        # Register broker via gRPC
        response = await grpc_client.register_broker(
            host=grpc_host,
            port=grpc_port,
            broker_id=BROKER_ID,
            broker_name="BrokerService"
        )
        
        if response.success:
            logger.info(f"Broker registered successfully with ID: {BROKER_ID}")
            return True
        else:
            logger.error(f"Broker registration failed: {response.message}")
            return False
            
    except Exception as e:
        logger.error(f"Error during broker registration via gRPC: {e}")
        return False

# --- RabbitMQ Consumer Running in Thread --- 
def run_rabbitmq_consumer(channel):
    """Target function to run pika's blocking consumer in a separate thread."""
    try:
        logger.info(f"Starting RabbitMQ consumer thread for queue: {channel.consumer_tags[0] if channel.consumer_tags else 'unknown'}")
        channel.start_consuming()
    except Exception as e:
        logger.error(f"Exception in RabbitMQ consumer thread: {e}")
    finally:
        if channel and channel.is_open:
            try:
                channel.stop_consuming()
            except Exception as e:
                logger.error(f"Error stopping RabbitMQ consumer: {e}")

# --- Main Execution ---
async def main():
    """Main entry point for the broker."""
    # Set up signal handlers
    def signal_handler():
        logger.info("Received termination signal, shutting down...")
        shutdown_event.set()
    
    # Register signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        # Register broker with server via gRPC
        if not await register_broker_via_grpc():
            logger.error("Failed to register broker with server. Exiting.")
            return
        
        # Set up RabbitMQ channels for different queues
        broker_input_channel = setup_rabbitmq_channel(BROKER_INPUT_QUEUE, handle_incoming_message)
        if not broker_input_channel:
            logger.error("Failed to set up broker input channel. Exiting.")
            return
            
        # Start RabbitMQ consumer threads
        broker_input_thread = threading.Thread(
            target=run_rabbitmq_consumer,
            args=(broker_input_channel,)
        )
        broker_input_thread.daemon = True
        broker_input_thread.start()
        
        logger.info("Broker started and running...")
        
        # Keep the main thread alive while handling signals
        while not shutdown_event.is_set():
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}")
    finally:
        logger.info("Broker shutdown complete")

if __name__ == "__main__":
    asyncio.run(main()) 