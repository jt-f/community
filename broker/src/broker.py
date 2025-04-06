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
import websockets
import signal

# Import shared models directly
from shared_models import (
    MessageType,
    ResponseStatus
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Get a logger for this module
log = logging.getLogger("broker")

# Define the broker name/ID
BROKER_ID = f"broker_{random.randint(1000, 9999)}"

# Reduce verbosity from pika library
logging.getLogger("pika").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.INFO) # Adjust websocket lib logging
log.info("Pika library logging level set to WARNING.")

# Connection details
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
WEBSOCKET_URL = os.getenv('WEBSOCKET_URL', 'ws://localhost:8765/ws')
BROKER_INPUT_QUEUE = "broker_input_queue"         
AGENT_METADATA_QUEUE = "agent_metadata_queue"
BROKER_OUTPUT_QUEUE = "broker_output_queue"       
SERVER_ADVERTISEMENT_QUEUE = "server_advertisement_queue"

# Dictionary to store registered agents - the only state the broker needs
registered_agents = {}  # agent_id -> agent info (capabilities, name, etc.)

# Global flag for shutdown coordination
shutdown_event = asyncio.Event()

def setup_rabbitmq_channel(queue_name, callback_function):
    """Set up a RabbitMQ channel and consumer."""
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()
        
        # Declare the queue, ensuring it exists
        channel.queue_declare(queue=queue_name, durable=True)
        
        # Set up the consumer
        channel.basic_consume(
            queue=queue_name,
            on_message_callback=lambda ch, method, properties, body: callback_function(ch, method, properties, body),
            auto_ack=False
        )
        
        log.info(f"Connected to RabbitMQ and consuming from {queue_name}")
        return channel
    except Exception as e:
        log.error(f"Failed to set up RabbitMQ channel for {queue_name}: {e}")
        return None

def publish_to_broker_output_queue(message_data):
    """Publish a message to the broker's output queue (read by the server)."""
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()
        
        # Ensure the queue exists
        channel.queue_declare(queue=BROKER_OUTPUT_QUEUE, durable=True)
        
        # Publish the message
        channel.basic_publish(
            exchange='',
            routing_key=BROKER_OUTPUT_QUEUE,
            body=json.dumps(message_data),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            )
        )
        
        log.info(f"Published message to {BROKER_OUTPUT_QUEUE}")
        
        # Clean up
        connection.close()
        return True
    except Exception as e:
        log.error(f"Failed to publish to {BROKER_OUTPUT_QUEUE}: {e}")
        return False

def handle_incoming_message(channel, method, properties, body):
    """Handle incoming chat messages from the BROKER_INPUT_QUEUE."""
    try:
        message_data = json.loads(body)
        message_type = message_data.get("message_type")
        sender_id = message_data.get("sender_id", "unknown") # Added sender_id for logging
        
        if message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
            log.info(f"Received message type {message_type} from {sender_id}")
            # Route message
            route_message(message_data)
            # Acknowledge the message was processed
            channel.basic_ack(delivery_tag=method.delivery_tag)
        elif message_type == MessageType.AGENT_STATUS_UPDATE:
            log.info(f"Received agent status update from {sender_id}")
            handle_agent_status_update(message_data)
            channel.basic_ack(delivery_tag=method.delivery_tag)
        else:
            log.warning(f"Received unsupported message type in broker input queue: {message_type}")
            # Acknowledge but skip processing
            channel.basic_ack(delivery_tag=method.delivery_tag)
    except json.JSONDecodeError:
        log.error(f"Invalid JSON in message: {body}")
        # Acknowledge but don't process invalid messages
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        log.error(f"Error processing incoming message: {e}")
        # Negative acknowledgment for failed processing
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def handle_agent_status_update(message_data):
    """Process agent status updates received via WebSocket."""
    log.info(f"[DEBUG] Received agent status update: {message_data}")
    
    if message_data.get("message_type") != MessageType.AGENT_STATUS_UPDATE:
        log.warning(f"Received non-status update message in status handler: {message_data.get('message_type')}")
        return
    
    agents_data = message_data.get("agents", [])
    is_full_update = message_data.get("is_full_update", False)
    
    if not agents_data:
        log.info("[DEBUG] Received empty agent status update.")
        return
        
    log.info(f"[DEBUG] Processing status update for {len(agents_data)} agents via WebSocket (is_full_update={is_full_update})")
    
    # If this is a full update, we could optionally clear our previous state
    if is_full_update:
        log.info("[DEBUG] This is a full update - current registered agents before update: " + 
                json.dumps({id: {"name": info["name"], "is_online": info["is_online"]} 
                          for id, info in registered_agents.items()}))
    
    updated_ids = set()
    # Update our internal state with the current agent statuses
    for agent in agents_data:
        agent_id = agent.get("agent_id")
        if not agent_id:
            log.warning("[DEBUG] Received agent status entry with no ID")
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
            log.info(f"[DEBUG] Added new agent from status update: {agent_name} ({agent_id}), Online: {is_online}")
        else:
            # Update existing agent's online status if it changed
            if registered_agents[agent_id].get("is_online") != is_online:
                old_status = registered_agents[agent_id].get("is_online")
                registered_agents[agent_id]["is_online"] = is_online
                log.info(f"[DEBUG] Updated agent status: {agent_name} ({agent_id}), Online status changed: {old_status} -> {is_online}")
            # Optionally update name if it changed
            if registered_agents[agent_id].get("name") != agent_name:
                old_name = registered_agents[agent_id].get("name")
                registered_agents[agent_id]["name"] = agent_name
                log.info(f"[DEBUG] Updated agent name: {agent_id} from '{old_name}' to '{agent_name}'")
    
    # If it was a full update, mark any agents not in the update as offline
    if is_full_update:
        log.info("[DEBUG] Processing full status update - marking missing agents as offline")
        agents_to_mark_offline = set(registered_agents.keys()) - updated_ids
        for agent_id in agents_to_mark_offline:
            if registered_agents[agent_id].get("is_online", False):
                registered_agents[agent_id]["is_online"] = False
                log.info(f"[DEBUG] Marked agent {registered_agents[agent_id].get('name', agent_id)} ({agent_id}) as offline (not in full update)")
    
    # Log the final state after processing
    online_agents = [agent_id for agent_id, info in registered_agents.items() if info.get("is_online", False)]
    log.info(f"[DEBUG] After status update: Total agents: {len(registered_agents)}, Online agents: {len(online_agents)}")
    log.info(f"[DEBUG] Online agents: {online_agents}")
    
    # Removed update to undefined agent_statuses
    # agent_statuses.update({id: info["is_online"] for id, info in registered_agents.items()})
    
    # Commented out block using undefined wait_for_online_callbacks
    # if online_agents and any(id in online_agents for id in wait_for_online_callbacks):
    #     log.info(f"[DEBUG] Notifying wait_for_online callbacks for newly online agents")
    #     for agent_id in list(wait_for_online_callbacks.keys()):
    #         if agent_id in online_agents:
    #             callbacks = wait_for_online_callbacks.pop(agent_id, [])
    #             for callback in callbacks:
    #                 callback()

def handle_control_message(channel, method, properties, body):
    """Handle control messages for the broker."""
    try:
        message_data = json.loads(body)
        message_type = message_data.get("message_type")
        
        # Process based on message type
        if message_type == MessageType.REGISTER_AGENT:
            handle_agent_registration(message_data)
        elif message_type == MessageType.CLIENT_DISCONNECTED:
            handle_client_disconnected(message_data)
        else:
            log.warning(f"Received unsupported control message type: {message_type}")
        
        # Acknowledge the message was processed
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except json.JSONDecodeError:
        log.error(f"Invalid JSON in control message: {body}")
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        log.error(f"Error processing control message: {e}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def handle_agent_registration(message_data):
    """Handles agent registration requests."""
    agent_id = message_data.get("agent_id")
    agent_name = message_data.get("agent_name", "Unknown Agent")
    client_id = message_data.get("_client_id")
    
    if not agent_id:
        log.error("Agent registration failed: Missing agent_id")
        return
    
    # Store agent information - this is the only state we need to maintain
    registered_agents[agent_id] = {
        "name": agent_name,
        "capabilities": message_data.get("capabilities", []),
        "registration_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_online": True
    }
    
    log.info(f"Agent registered: {agent_name} (ID: {agent_id})")
    
    # Prepare registration response
    response = {
        "message_type": MessageType.REGISTER_AGENT_RESPONSE,
        "status": ResponseStatus.SUCCESS,
        "agent_id": agent_id,
        "message": "Agent registered successfully",
    }
    
    # Add client_id for routing back to the correct client (if provided)
    if client_id:
        response["_client_id"] = client_id
    
    # Send response back to the server via the broker output queue
    publish_to_broker_output_queue(response)

def handle_client_disconnected(message_data):
    """Handles client disconnection notification."""
    agent_id = message_data.get("agent_id")
    
    # If this is an agent disconnection and we know about this agent
    if agent_id and agent_id in registered_agents:
        log.info(f"Unregistering agent {agent_id} due to client disconnection")
        
        # Mark agent as offline but keep its registration
        registered_agents[agent_id]["is_online"] = False
        log.info(f"Agent {agent_id} marked as offline")

def handle_server_advertisement(channel, method, properties, body):
    """Handle server availability advertisement."""
    try:
        message_data = json.loads(body)
        if message_data.get("message_type") == MessageType.SERVER_AVAILABLE:
            log.info(f"Server available at {message_data.get('websocket_url')}")
    except Exception as e:
        log.error(f"Error handling server advertisement: {e}")
    finally:
        channel.basic_ack(delivery_tag=method.delivery_tag)

def route_message(message_data):
    """Route messages to the appropriate recipients.
    If receiver_id is 'broadcast' or not specified, randomly selects an online agent.
    Otherwise, attempts direct routing to the specified agent.
    
    Never routes a message back to the agent who sent it.
    All messages are published to BROKER_OUTPUT_QUEUE with appropriate receiver_id set.
    """
    message_type = message_data.get("message_type")
    sender_id = message_data.get("sender_id", "unknown")

    log.info(f"[DEBUG] Routing message from {sender_id} type={message_type}")
    
    # Create a clean copy of the message for routing
    outgoing_message = dict(message_data)
    
    # Remove any routing metadata fields that might be present
    for field in ["_broadcast", "_target_agent_id", "_client_id"]:
        if field in outgoing_message:
            outgoing_message.pop(field)

    # Extract original text payload for error messages
    original_text = message_data.get("text_payload", "")
    truncated_text = (original_text[:20] + '...') if len(original_text) > 20 else original_text

    # Thoroughly log the state of all agents
    log.info(f"[DEBUG] All registered agents: {json.dumps(registered_agents)}")
    
    # Log all agent statuses
    for agent_id, info in registered_agents.items():
        log.info(f"[DEBUG] Agent {agent_id}: name={info.get('name', 'unknown')}, is_online={info.get('is_online', False)}")
    
    # Get list of online agents, EXCLUDING the sender if it's an agent
    online_agents = [
        agent_id for agent_id, info in registered_agents.items()
        if info.get("is_online", False) and agent_id != sender_id  # Exclude the sender
    ]

    log.info(f"[DEBUG] Online agents (excluding sender): {online_agents}")
    
    if online_agents:
        # Randomly select an agent (that is not the sender)
        chosen_agent_id = random.choice(online_agents)
        
        # Set the receiver_id to the chosen agent
        outgoing_message["receiver_id"] = chosen_agent_id
        
        # Send the message
        log.info(f"Randomly routing message '{truncated_text}' from {sender_id} to agent {chosen_agent_id}")
        publish_to_broker_output_queue(outgoing_message)
        return
    else:
        # Count how many total online agents we have
        all_online_agents = [
            agent_id for agent_id, info in registered_agents.items()
            if info.get("is_online", False)
        ]
        
        log.info(f"[DEBUG] All online agents (including sender): {all_online_agents}")
        
        # If sender is the only online agent
        if sender_id in all_online_agents and len(all_online_agents) == 1:
            # Get the agent's name for the error message
            agent_name = registered_agents.get(sender_id, {}).get("name", sender_id) # Fallback to ID if name not found
            log.warning(f"Only the sending agent {agent_name} ({sender_id}) is online. Cannot route message '{truncated_text}' to another agent.")
            error_response = {
                "message_type": MessageType.ERROR,
                "sender_id": "BrokerService", # Keep sender as Broker
                "receiver_id": "Server",     # Send error back to the server
                "text_payload": f"The sender is the only online agent. No other agents are available to receive the message."
            }
            publish_to_broker_output_queue(error_response)
            return
        else:
            # No online agents available
            error_response = {
                "message_type": MessageType.ERROR,
                "sender_id": "BrokerService", # Keep sender as Broker
                "receiver_id": sender_id if sender_id != "unknown" else "server",
                "text_payload": f"No online agents available to handle the message."
            }
            publish_to_broker_output_queue(error_response)
            log.warning(f"Could not route message '{truncated_text}' from {sender_id}: No online agents found")
            return

async def websocket_listener():
    """Connects to the server via WebSocket and listens for messages."""
    while not shutdown_event.is_set():
        try:
            async with websockets.connect(WEBSOCKET_URL) as websocket:
                log.info(f"Connected to WebSocket server at {WEBSOCKET_URL}")
                
                # Register as broker with just the name
                register_message = {
                    "message_type": MessageType.REGISTER_BROKER,
                    "broker_name": "BrokerService"  # Just provide the name
                }
                await websocket.send(json.dumps(register_message))
                log.info("Sent REGISTER_BROKER message")
                
                # Wait for registration response
                response = await websocket.recv()
                response_data = json.loads(response)
                
                if response_data.get("message_type") == MessageType.REGISTER_BROKER_RESPONSE:
                    # Store the assigned broker ID
                    global BROKER_ID
                    BROKER_ID = response_data["broker_id"]
                    log.info(f"Registered as broker with ID: {BROKER_ID}")
                else:
                    log.error(f"Failed to register broker: {response_data}")
                    continue
                
                # Listen for messages
                while not shutdown_event.is_set():
                    try:
                        message_str = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        message_data = json.loads(message_str)
                        message_type = message_data.get("message_type")
                        
                        if message_type == MessageType.AGENT_STATUS_UPDATE:
                            handle_agent_status_update(message_data)
                        elif message_type in [MessageType.PING, MessageType.SERVER_HEARTBEAT]: # Respond to both PING and HEARTBEAT
                            # Respond to PING/HEARTBEAT from server
                            pong_message = {"message_type": MessageType.PONG}
                            await websocket.send(json.dumps(pong_message))
                            log.info(f"Received {message_type}, sent PONG to server")
                        elif message_type == MessageType.ERROR:
                            # Server might send ERROR if it doesn't handle our PING; ignore it.
                            log.debug(f"Received ERROR message via WebSocket, likely due to PING: {message_data.get('text_payload')}")
                            pass # Ignore these errors
                        else:
                            log.warning(f"Received unhandled WebSocket message type: {message_type}")
                            
                    except asyncio.TimeoutError:
                        # No message received, just continue listening
                        continue
                    except websockets.exceptions.ConnectionClosedOK:
                        log.info("WebSocket connection closed normally.")
                        break # Exit inner loop to reconnect
                    except websockets.exceptions.ConnectionClosedError as e:
                        log.error(f"WebSocket connection closed with error: {e}")
                        break # Exit inner loop to reconnect
                    except json.JSONDecodeError:
                        log.error(f"Invalid JSON received via WebSocket: {message_str}")
                    except Exception as e:
                        log.exception(f"Error processing WebSocket message: {e}")
        
        except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.InvalidURI, ConnectionRefusedError, OSError) as e:
            log.error(f"WebSocket connection failed: {e}")
        except Exception as e:
            log.exception(f"Unexpected error in websocket_listener: {e}")
            
        if not shutdown_event.is_set():
            log.info("Attempting to reconnect WebSocket in 5 seconds...")
            await asyncio.sleep(5)
            
    log.info("WebSocket listener shutting down.")

# REMOVED request_agent_status function
# ...

# --- RabbitMQ Consumer Running in Thread --- 
def run_rabbitmq_consumer(channel):
    """Target function to run pika's blocking consumer in a separate thread."""
    try:
        log.info(f"Starting RabbitMQ consumer thread for queue: {channel.consumer_tags[0] if channel.consumer_tags else 'unknown'}")
        channel.start_consuming()
    except Exception as e:
        log.error(f"Exception in RabbitMQ consumer thread: {e}")
    finally:
        if channel and channel.is_open:
            try:
                channel.stop_consuming()
                channel.close()
            except Exception as close_exc:
                log.error(f"Error closing RabbitMQ channel in thread: {close_exc}")
        log.info("RabbitMQ consumer thread finished.")

async def main_async():
    """Main async function to run WebSocket listener and RabbitMQ consumers."""
    log.info(f"Starting async message broker service (ID: {BROKER_ID})")
    
    # --- Setup RabbitMQ Channels (Synchronous part) ---
    # Note: We setup channels here, but run consumers in threads
    channels_to_run = {}
    try:
        incoming_channel = setup_rabbitmq_channel(BROKER_INPUT_QUEUE, handle_incoming_message)
        control_channel = setup_rabbitmq_channel(AGENT_METADATA_QUEUE, handle_control_message)
        advertisement_channel = setup_rabbitmq_channel(SERVER_ADVERTISEMENT_QUEUE, handle_server_advertisement)
        
        if incoming_channel:
            channels_to_run[incoming_channel] = "incoming_channel"
        if control_channel:
            channels_to_run[control_channel] = "control_channel"
        if advertisement_channel:
            channels_to_run[advertisement_channel] = "advertisement_channel"
            
        if not channels_to_run:
             raise RuntimeError("Failed to set up any RabbitMQ channels.")
             
    except Exception as setup_exc:
        log.error(f"Fatal error setting up RabbitMQ: {setup_exc}")
        return # Exit if RabbitMQ setup fails
    
    # --- Start RabbitMQ Consumers in Threads --- 
    consumer_threads = []
    for channel, name in channels_to_run.items():
        thread = threading.Thread(target=run_rabbitmq_consumer, args=(channel,), daemon=True, name=f"RabbitMQ-{name}")
        thread.start()
        consumer_threads.append(thread)
        log.info(f"Started RabbitMQ consumer thread for {name}")
    
    # --- Start WebSocket Listener Task --- 
    websocket_task = asyncio.create_task(websocket_listener())
    log.info("Started WebSocket listener task.")
    
    log.info("Broker service components running. Waiting for shutdown signal...")
    
    # --- Wait for Shutdown --- 
    await shutdown_event.wait() # Wait until the shutdown event is set
    
    # --- Initiate Graceful Shutdown --- 
    log.info("Shutdown signal received. Stopping components...")
    
    # Stop WebSocket listener task
    websocket_task.cancel()
    try:
        await websocket_task
    except asyncio.CancelledError:
        log.info("WebSocket listener task cancelled.")
        
    # Stop RabbitMQ consumers (by closing channels from main thread)
    log.info("Stopping RabbitMQ consumer threads...")
    for channel, name in channels_to_run.items():
        if channel and channel.is_open:
            try:
                # Closing the channel from here should interrupt the blocking start_consuming() in the thread
                channel.close()
                log.info(f"Closed RabbitMQ channel for {name}")
            except Exception as e:
                log.error(f"Error closing RabbitMQ channel {name} during shutdown: {e}")
                
    # Wait for consumer threads to finish (optional, with timeout)
    for thread in consumer_threads:
        thread.join(timeout=5.0)
        if thread.is_alive():
            log.warning(f"RabbitMQ consumer thread {thread.name} did not exit cleanly.")

    log.info("Broker service shut down successfully.")

def main():
    """Sets up signal handling and runs the main async function."""
    loop = asyncio.get_event_loop()
    
    # Add signal handlers to set the shutdown_event
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)
        
    try:
        loop.run_until_complete(main_async())
    finally:
        loop.close()
        log.info("Asyncio event loop closed.")

if __name__ == "__main__":
    import signal # Import signal here for the main block
    main() 