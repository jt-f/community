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
from shared_models import setup_logging, MessageType, ResponseStatus
import grpc_client  # Import the gRPC client module


logger = setup_logging(__name__)

# Define the broker name/ID
BROKER_ID = f"broker_{random.randint(1000, 9999)}"

# Reduce verbosity from pika library
logging.getLogger("pika").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.INFO) # Adjust websocket lib logging
logger.info("Pika library logging level set to WARNING.")

# Connection details
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
WEBSOCKET_URL = os.getenv('WEBSOCKET_URL', 'ws://localhost:8765/ws')
BROKER_INPUT_QUEUE = "broker_input_queue"         
AGENT_METADATA_QUEUE = "agent_metadata_queue"
SERVER_INPUT_QUEUE = "server_input_queue" # Broker now sends responses/routed messages here
SERVER_ADVERTISEMENT_QUEUE = "server_advertisement_queue"

# Dictionary to store registered agents - the only state the broker needs
registered_agents = {}  # agent_id -> agent info (capabilities, name, etc.)

# Global flag for shutdown coordination
shutdown_event = asyncio.Event()

# Global flag to track when we need to request agent status
_need_agent_status_update = False


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
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
        channel = connection.channel()

        # Ensure the queue exists (server should primarily declare it)
        channel.queue_declare(queue=SERVER_INPUT_QUEUE, durable=True)

        # Publish the message
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

def handle_incoming_message(channel, method, properties, body):
    """Handle incoming chat messages from the BROKER_INPUT_QUEUE."""
    try:
        message_data = json.loads(body)
        message_type = message_data.get("message_type")
        sender_id = message_data.get("sender_id", "unknown") # Added sender_id for logging
        receiver_id = message_data.get("receiver_id") # Get receiver_id
        routing_status = message_data.get("routing_status", "unknown")
        
        if message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
            logger.info(f"Incoming {message_type} message {message_data.get('message_id','N/A')} from {sender_id} : '{message_data.get('text_payload','N/A')}' (routing_status={routing_status})")
            
            # Check if the message has a receiver_id that looks like an agent but is unknown
            if (receiver_id and receiver_id.startswith("agent_") and 
                receiver_id not in registered_agents):
                logger.warning(f"Message {message_data.get('message_id', 'N/A')} references unknown agent: {receiver_id}")
                # Request agent status update from server asynchronously
                asyncio.create_task(request_agent_status())
            
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

def handle_agent_status_update(message_data):
    """Process agent status updates received via WebSocket."""
    logger.debug(f"[DEBUG] Received agent status update: {message_data}")
    
    if message_data.get("message_type") != MessageType.AGENT_STATUS_UPDATE:
        logger.warning(f"Received non-status update message in status handler: {message_data.get('message_type')}")
        return
    
    agents_data = message_data.get("agents", [])
    is_full_update = message_data.get("is_full_update", False)
    
    if not agents_data:
        logger.debug("[DEBUG] Received empty agent status update.")
        return
        
    logger.debug(f"[DEBUG] Processing status update for {len(agents_data)} agents via WebSocket (is_full_update={is_full_update})")
    
    # If this is a full update, we could optionally clear our previous state
    if is_full_update:
        logger.debug("[DEBUG] This is a full update - current registered agents before update: " + 
                json.dumps({id: {"name": info["name"], "is_online": info["is_online"]} 
                          for id, info in registered_agents.items()}))
    
    updated_ids = set()
    # Update our internal state with the current agent statuses
    for agent in agents_data:
        agent_id = agent.get("agent_id")
        if not agent_id:
            logger.warning("[DEBUG] Received agent status entry with no ID")
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
            logger.debug(f"[DEBUG] Added new agent from status update: {agent_name} ({agent_id}), Online: {is_online}")
        else:
            # Update existing agent's online status if it changed
            if registered_agents[agent_id].get("is_online") != is_online:
                old_status = registered_agents[agent_id].get("is_online")
                registered_agents[agent_id]["is_online"] = is_online
                logger.debug(f"[DEBUG] Updated agent status: {agent_name} ({agent_id}), Online status changed: {old_status} -> {is_online}")
            # Optionally update name if it changed
            if registered_agents[agent_id].get("name") != agent_name:
                old_name = registered_agents[agent_id].get("name")
                registered_agents[agent_id]["name"] = agent_name
                logger.debug(f"[DEBUG] Updated agent name: {agent_id} from '{old_name}' to '{agent_name}'")
    
    # If it was a full update, mark any agents not in the update as offline
    if is_full_update:
        logger.debug("[DEBUG] Processing full status update - marking missing agents as offline")
        agents_to_mark_offline = set(registered_agents.keys()) - updated_ids
        for agent_id in agents_to_mark_offline:
            if registered_agents[agent_id].get("is_online", False):
                registered_agents[agent_id]["is_online"] = False
                logger.debug(f"[DEBUG] Marked agent {registered_agents[agent_id].get('name', agent_id)} ({agent_id}) as offline (not in full update)")
    
    # Log the final state after processing
    online_agents = [agent_id for agent_id, info in registered_agents.items() if info.get("is_online", False)]
    logger.debug(f"[DEBUG] After status update: Total agents: {len(registered_agents)}, Online agents: {len(online_agents)}")
    logger.debug(f"[DEBUG] Online agents: {online_agents}")
    
    # Removed update to undefined agent_statuses
    # agent_statuses.update({id: info["is_online"] for id, info in registered_agents.items()})
    
    # Commented out block using undefined wait_for_online_callbacks
    # if online_agents and any(id in online_agents for id in wait_for_online_callbacks):
    #     logger.debug(f"[DEBUG] Notifying wait_for_online callbacks for newly online agents")
    #     for agent_id in list(wait_for_online_callbacks.keys()):
    #         if agent_id in online_agents:
    #             callbacks = wait_for_online_callbacks.pop(agent_id, [])
    #             for callback in callbacks:
    #                 callback()

# Create a new async version of handle_agent_status_update for gRPC
async def handle_agent_status_update_async(message_data):
    """Async wrapper for handle_agent_status_update to be used with gRPC."""
    handle_agent_status_update(message_data)

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
            logger.warning(f"Received unsupported control message type: {message_type}")
        
        # Acknowledge the message was processed
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in control message: {body}")
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error(f"Error processing control message: {e}")
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def handle_agent_registration(message_data):
    """Handles agent registration requests."""
    agent_id = message_data.get("agent_id")
    agent_name = message_data.get("agent_name", "Unknown Agent")
    client_id = message_data.get("_client_id")
    
    if not agent_id:
        logger.error("Agent registration failed: Missing agent_id")
        return
    
    # Store agent information - this is the only state we need to maintain
    registered_agents[agent_id] = {
        "name": agent_name,
        "capabilities": message_data.get("capabilities", []),
        "registration_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_online": True
    }
    
    logger.info(f"Agent registered: {agent_name} (ID: {agent_id})")
    
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
    
    # Send response back to the server via the server input queue
    publish_to_server_input_queue(response)

def handle_client_disconnected(message_data):
    """Handles client disconnection notification."""
    agent_id = message_data.get("agent_id")
    
    # If this is an agent disconnection and we know about this agent
    if agent_id and agent_id in registered_agents:
        logger.info(f"Unregistering agent {agent_id} due to client disconnection")
        
        # Mark agent as offline but keep its registration
        registered_agents[agent_id]["is_online"] = False
        logger.info(f"Agent {agent_id} marked as offline")

def handle_server_advertisement(channel, method, properties, body):
    """Handle server availability advertisement."""
    try:
        message_data = json.loads(body)
        if message_data.get("message_type") == MessageType.SERVER_AVAILABLE:
            logger.info(f"Server available at {message_data.get('websocket_url')}")
    except Exception as e:
        logger.error(f"Error handling server advertisement: {e}")
    finally:
        channel.basic_ack(delivery_tag=method.delivery_tag)

async def request_agent_status():
    """Request agent status update from the server via WebSocket.
    This is called when the broker encounters an unknown agent ID.
    """
    # Global variable to track the last time we requested agent status
    # to prevent flooding the server with requests
    global _last_agent_status_request
    current_time = time.time()
    
    # Don't request more than once every 5 seconds
    if hasattr(request_agent_status, '_last_request_time') and \
       current_time - request_agent_status._last_request_time < 5:
        logger.debug("Skipping agent status request due to rate limiting")
        return
    
    # Store the current time as the last request time
    request_agent_status._last_request_time = current_time
    
    # Create a websocket connection if we're not already in a websocket context
    try:
        # Send the request message to the server
        logger.info("Requesting agent status update from server")
        request_message = {
            "message_type": MessageType.REQUEST_AGENT_STATUS,
            "sender_id": BROKER_ID,
            "timestamp": datetime.now().isoformat()
        }
        
        # Try to find an active websocket in the current active connections
        # This is a simplified approach assuming websocket_listener has a valid connection
        # A more robust solution would involve a dedicated websocket manager
        
        for task in asyncio.all_tasks():
            task_name = task.get_name() 
            if task_name == "websocket_listener" and not task.done():
                # The websocket_listener task is running
                logger.debug("Found active websocket_listener task")
                # We can't access its websocket directly,
                # so we'll set a flag to request status on next message
                global _need_agent_status_update
                _need_agent_status_update = True
                return
        
        logger.warning("No active websocket connection found to request agent status")
        # Schedule an attempt to reconnect the websocket if needed
        # This assumes the websocket_listener will reconnect itself
        
    except Exception as e:
        logger.error(f"Error requesting agent status: {e}")

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
        asyncio.create_task(request_agent_status())
    
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
    
    # Get list of online agents, EXCLUDING the sender if it's an agent
    online_agents = [
        agent_id for agent_id, info in registered_agents.items()
        if info.get("is_online", False) and agent_id != sender_id  # Exclude the sender
    ]

    logger.debug(f"[DEBUG] Online agents (excluding sender): {online_agents}")
    
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
        
        logger.debug(f"[DEBUG] All online agents (including sender): {all_online_agents}")
        
        # If sender is the only online agent
        if sender_id in all_online_agents and len(all_online_agents) == 1:
            # Get the agent's name for the error message
            agent_name = registered_agents.get(sender_id, {}).get("name", sender_id) # Fallback to ID if name not found
            error_response = {
                "message_id": message_id,
                "message_type": MessageType.ERROR,
                "sender_id": sender_id,
                "receiver_id": "Server",     # Send error back to the server
                "routing_status": "Only the sending agent is online. Routing failed.",   # Mark as routing error
                "text_payload": f"{original_text}"
            }
            publish_to_server_input_queue(error_response)
            logger.warning(f"Only the sending agent {agent_name} ({sender_id}) is online. Cannot route message '{truncated_text}' to another agent.")

            return
        else:
            # No online agents available
            error_response = {
                "message_id": message_id,
                "message_type": MessageType.ERROR,
                "sender_id": sender_id,
                "receiver_id": "Server", # Send error back to the server
                "routing_status": "No online agents available. Routing failed.", # Mark as routing error
                "text_payload": f"{original_text}"
            }
            publish_to_server_input_queue(error_response)
            logger.warning(f"Could not route message '{truncated_text}' from {sender_id}: No online agents found")
            return

async def websocket_listener():
    """Connects to the server via WebSocket and listens for messages."""
    global BROKER_ID, _need_agent_status_update  # Move both global declarations to the beginning of the function
    
    # Variables to track gRPC configuration
    grpc_enabled = False
    grpc_host = None
    grpc_port = None
    
    while not shutdown_event.is_set():
        try:
            async with websockets.connect(WEBSOCKET_URL) as websocket:
                logger.info(f"Connected to WebSocket server at {WEBSOCKET_URL}")
                
                # Register as broker with just the name
                register_message = {
                    "message_type": MessageType.REGISTER_BROKER,
                    "broker_name": "BrokerService"  # Just provide the name
                }
                await websocket.send(json.dumps(register_message))
                logger.info("Sent REGISTER_BROKER message")
                
                # Wait for registration response
                response = await websocket.recv()
                response_data = json.loads(response)
                
                if response_data.get("message_type") == MessageType.REGISTER_BROKER_RESPONSE:
                    # Store the assigned broker ID
                    BROKER_ID = response_data["broker_id"]
                    logger.info(f"Registered as broker with ID: {BROKER_ID}")
                    
                    # Get gRPC configuration for agent status updates
                    grpc_host = response_data.get("grpc_host", "localhost")
                    grpc_port = int(response_data.get("grpc_port", "50051"))
                    logger.info(f"Server provided gRPC endpoint at {grpc_host}:{grpc_port}")
                    
                    # Set up gRPC callback to handle agent status updates
                    grpc_client.set_agent_status_callback(handle_agent_status_update_async)
                    
                    # Start gRPC client in a separate task
                    asyncio.create_task(grpc_client.connect_to_grpc_server(
                        host=grpc_host,
                        port=grpc_port,
                        broker_id=BROKER_ID
                    ))
                else:
                    logger.error(f"Failed to register broker: {response_data}")
                    continue
                
                # Listen for messages via WebSocket
                while not shutdown_event.is_set():
                    try:
                        # Check if we need to request agent status
                        if _need_agent_status_update:
                            logger.info("Requesting agent status update via gRPC")
                            asyncio.create_task(grpc_client.request_agent_status(
                                host=grpc_host,
                                port=grpc_port,
                                broker_id=BROKER_ID
                            ))
                            _need_agent_status_update = False
                            logger.info("Agent status update requested")

                        message_str = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        message_data = json.loads(message_str)
                        message_type = message_data.get("message_type")
                        
                        # Never handle agent status updates via WebSocket - always use gRPC
                        if message_type in [MessageType.PING, MessageType.SERVER_HEARTBEAT]: # Respond to both PING and HEARTBEAT
                            # Respond to PING/HEARTBEAT from server
                            pong_message = {"message_type": MessageType.PONG}
                            await websocket.send(json.dumps(pong_message))
                            logger.debug(f"Received {message_type}, sent PONG to server")
                        elif message_type == MessageType.ERROR:
                            # Server might send ERROR if it doesn't handle our PING; ignore it.
                            logger.debug(f"Received ERROR message via WebSocket, likely due to PING: {message_data.get('text_payload')}")
                            pass # Ignore these errors
                        elif message_type == MessageType.AGENT_STATUS_UPDATE:
                            # Ignore agent status updates via WebSocket - we use gRPC now
                            logger.debug("Received agent status update via WebSocket - ignoring as we use gRPC")
                        else:
                            logger.warning(f"Received unhandled WebSocket message type: {message_type}")
                            
                    except asyncio.TimeoutError:
                        # No message received, just continue listening
                        continue
                    except websockets.exceptions.ConnectionClosedOK:
                        logger.info("WebSocket connection closed normally.")
                        break # Exit inner loop to reconnect
                    except websockets.exceptions.ConnectionClosedError as e:
                        logger.error(f"WebSocket connection closed with error: {e}")
                        break # Exit inner loop to reconnect
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON received via WebSocket: {message_str}")
                    except Exception as e:
                        logger.exception(f"Error processing WebSocket message: {e}")
        
        except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.InvalidURI, ConnectionRefusedError, OSError) as e:
            logger.error(f"WebSocket connection failed: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error in websocket_listener: {e}")
            
        if not shutdown_event.is_set():
            logger.info("Attempting to reconnect WebSocket in 5 seconds...")
            await asyncio.sleep(5)
            
    logger.info("WebSocket listener shutting down.")

# REMOVED request_agent_status function
# ...

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
                channel.close()
            except Exception as close_exc:
                logger.error(f"Error closing RabbitMQ channel in thread: {close_exc}")
        logger.info("RabbitMQ consumer thread finished.")

async def main_async():
    """Main async function to run WebSocket listener and RabbitMQ consumers."""
    logger.info(f"Starting async message broker service (ID: {BROKER_ID})")
    
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
        logger.error(f"Fatal error setting up RabbitMQ: {setup_exc}")
        return # Exit if RabbitMQ setup fails
    
    # --- Start RabbitMQ Consumers in Threads --- 
    consumer_threads = []
    for channel, name in channels_to_run.items():
        thread = threading.Thread(target=run_rabbitmq_consumer, args=(channel,), daemon=True, name=f"RabbitMQ-{name}")
        thread.start()
        consumer_threads.append(thread)
        logger.info(f"Started RabbitMQ consumer thread for {name}")
    
    # --- Start WebSocket Listener Task --- 
    websocket_task = asyncio.create_task(websocket_listener())
    logger.info("Started WebSocket listener task.")
    
    logger.info("Broker service components running. Waiting for shutdown signal...")
    
    # --- Wait for Shutdown --- 
    await shutdown_event.wait() # Wait until the shutdown event is set
    
    # --- Initiate Graceful Shutdown --- 
    logger.info("Shutdown signal received. Stopping components...")
    
    # Stop WebSocket listener task
    websocket_task.cancel()
    try:
        await websocket_task
    except asyncio.CancelledError:
        logger.info("WebSocket listener task cancelled.")
        
    # Stop RabbitMQ consumers (by closing channels from main thread)
    logger.info("Stopping RabbitMQ consumer threads...")
    for channel, name in channels_to_run.items():
        if channel and channel.is_open:
            try:
                # Closing the channel from here should interrupt the blocking start_consuming() in the thread
                channel.close()
                logger.info(f"Closed RabbitMQ channel for {name}")
            except Exception as e:
                logger.error(f"Error closing RabbitMQ channel {name} during shutdown: {e}")
                
    # Wait for consumer threads to finish (optional, with timeout)
    for thread in consumer_threads:
        thread.join(timeout=5.0)
        if thread.is_alive():
            logger.warning(f"RabbitMQ consumer thread {thread.name} did not exit cleanly.")

    logger.info("Broker service shut down successfully.")

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
        logger.info("Asyncio event loop closed.")

if __name__ == "__main__":
    import signal # Import signal here for the main block
    main() 