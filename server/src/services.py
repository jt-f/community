import asyncio
import json
import pika
from datetime import datetime
from fastapi import WebSocket # Added for _safe_send_websocket type hint
import uuid
import os

# Import shared models, config, state, and utils
from shared_models import MessageType, setup_logging, ResponseStatus
import config
import state
import rabbitmq_utils
import agent_manager

# Import the necessary publish functions explicitly
from rabbitmq_utils import publish_to_agent_queue, publish_to_broker_input_queue

# Create shutdown event for graceful service termination
shutdown_event = asyncio.Event()

# Create lock for thread-safe access to agent connections
agent_connections_lock = asyncio.Lock()

logger = setup_logging(__name__)

# --- Helper Functions ---

def _prepare_message_for_client(response_data: dict, routing_status: str | None = None) -> dict:
    """Creates a copy of the response data, removes internal keys, and adds routing status."""
    message_copy = response_data.copy()
    
    # Remove internal RabbitMQ routing keys first
    for key in ["_broadcast", "_target_agent_id", "_client_id"]:
        message_copy.pop(key, None)
    
    # Add or preserve the routing status for the frontend
    if routing_status:
        # Use provided routing_status
        message_copy["routing_status"] = routing_status
    elif "routing_status" not in message_copy:
        # Only set default if no status exists
        message_copy["routing_status"] = "unknown"
    
    return message_copy

async def _safe_send_websocket(ws: WebSocket, payload_str: str, client_desc: str) -> bool:
    """Sends data to a WebSocket, handling exceptions and logging."""
    try:
        await ws.send_text(payload_str)
        logger.debug(f"Successfully sent message to {client_desc}")
        return True
    except Exception as e:
        logger.error(f"Error sending message to {client_desc}: {e}. Connection assumed lost.")
        return False

async def _broadcast_to_frontends(payload_str: str, message_type: str, origin_desc: str = "server_input_consumer", message_id: str = "N/A"):
    """Helper to broadcast a message payload (as JSON string) to all connected frontends."""
    disconnected_frontend = set()
    frontend_count = len(state.frontend_connections)
    if frontend_count > 0:
        logger.info(f"Broadcasting message {message_id} from {origin_desc} to {frontend_count} frontend clients: {payload_str}")
        # Iterate over a copy of the set to avoid modification during iteration
        for fe_ws in list(state.frontend_connections):
            # Get the client_id for better logging
            fe_client_id = getattr(fe_ws, 'client_id', '?')
            fe_client_desc = f"frontend client {fe_client_id}"
            if not await _safe_send_websocket(fe_ws, payload_str, fe_client_desc):
                disconnected_frontend.add(fe_ws)
        
        # Clean up disconnected frontends immediately
        if disconnected_frontend:
            state.frontend_connections -= disconnected_frontend
            logger.info(f"Removed {len(disconnected_frontend)} disconnected frontend clients during broadcast.")
    else:
        logger.info("No frontend clients connected, skipping broadcast.")

# --- Server Input Consumer Service ---

async def _process_server_input_message(message_data: dict):
    """Processes a single message received from the server_input_queue.
    
    Messages will have routing_status field to indicate the state:
    - 'pending': Not yet routed by broker
    - 'routed': Successfully routed by broker with receiver_id set
    - 'error': Failed routing with error information
    """
    message_type = message_data.get("message_type")
    sender_id = message_data.get("sender_id", "unknown")
    receiver_id = message_data.get("receiver_id")
    # Assume the broker includes the ID of the original message that failed in the error payload
    original_message_id = message_data.get("message_id", "N/A") 
    routing_status = message_data.get("routing_status", "error") # Default to error if not specified

    try:
        # --- Priority Case: Direct message from Broker with routing error ---
        if message_type == MessageType.ERROR and receiver_id == "Server":
            logger.info(f"Received error message from broker for message {original_message_id} from {sender_id}: {message_data}")
            # Broker now sends original text in text_payload and error in routing_status_message
            original_text = message_data.get('text_payload') # This should be the original text
            error_description = message_data.get('routing_status_message', 'Unknown routing error') 
            final_routing_status = message_data.get("routing_status", "error") # e.g., 'error', 'routing_failed'
            
            # Log the received error notification accurately
            logger.warning(f"Routing failure notification for message {original_message_id} from {sender_id}. Reason: {error_description} (Status: {final_routing_status})")

            # Construct the status update message for the frontend
            # IMPORTANT: Include the ORIGINAL text payload received from the broker
            message_for_frontend = {
                "message_id": original_message_id, # ID of the message that failed routing
                "sender_id": sender_id,          # Original sender of the failed message
                "receiver_id": None,             # No specific receiver for the status update itself
                "message_type": MessageType.ERROR, # Keep type as ERROR to signal failure
                "text_payload": original_text,   # <-- Use the original text payload!
                "routing_status": final_routing_status, # Use the status from the broker's message
                "routing_status_message": error_description, # Put the detailed error description here
                "send_timestamp": message_data.get("send_timestamp", datetime.now().isoformat())
            }

            # Prepare and broadcast
            prepared_message = _prepare_message_for_client(message_for_frontend, routing_status=message_for_frontend["routing_status"])
            payload_str = json.dumps(prepared_message)
            await _broadcast_to_frontends(payload_str, MessageType.ERROR, "Server (processing routing error)", original_message_id)
        
        # --- Case 2: Message with pending routing status ---  
        elif routing_status == "pending":
            logger.info(f"Message ID {original_message_id} from {sender_id} requires routing (status=pending).")

            # Message is already broadcast to frontends with pending status before being queued
            # Just forward to broker for routing
            if publish_to_broker_input_queue(message_data):
                logger.info(f"Published message ID {original_message_id} from {sender_id} to broker_input_queue.")
            else:
                logger.error(f"Failed to publish message ID {original_message_id} from {sender_id} to broker_input_queue.")

        # --- Case 3: Message has been routed by broker ---
        elif routing_status == "routed" and receiver_id is not None:
            logger.info(f"Received routed message {original_message_id} on server_input_queue for final receiver {receiver_id}.")

            # Broadcast as routed to frontends so they can update message status
            message_for_frontend = _prepare_message_for_client(message_data, routing_status="routed")
            payload_str = json.dumps(message_for_frontend)
            await _broadcast_to_frontends(payload_str, message_type, f"Server (routed to {receiver_id})", original_message_id)

            # Forward to the final agent recipient
            if receiver_id in state.agent_statuses:
                if state.agent_statuses[receiver_id].is_online:
                    if publish_to_agent_queue(receiver_id, message_data):
                        logger.info(f"Published routed message {original_message_id} to {receiver_id}'s queue.")
                    else:
                        logger.error(f"Failed to publish routed message {original_message_id} to agent {receiver_id}'s queue.")
                else:
                    logger.warning(f"Routed message ID intended for agent {receiver_id}, but agent is offline.")
                    # Notify broker and original sender that agent is offline
                    error_resp = {
                        "message_type": MessageType.ERROR,
                        "sender_id": "server",
                        "receiver_id": message_data.get("sender_id", "unknown"),
                        "routing_status": "error",
                        "text_payload": f"Agent {receiver_id} is offline. Message could not be delivered."
                    }
                    if publish_to_broker_input_queue(error_resp):
                        logger.info(f"Sent agent offline error for message {original_message_id} to broker.")
            elif receiver_id == "Server":
                 # A message explicitly routed to the server? Handle server-specific functionality.
                 logger.info(f"Message {original_message_id} from {sender_id} routed to the Server. Server-side processing.")
            else:
                # Broker routed to an unknown agent ID
                logger.warning(f"Routed message {original_message_id} has unknown receiver_id: {receiver_id}. Cannot deliver.")
                logger.warning(f"Known agents: {list(state.agent_statuses.keys())}")

        # --- Case 4: Unrecognized message or routing status ---
        else:
            logger.warning(f"Unrecognized message: sender={sender_id}, routing_status={routing_status}, receiver={receiver_id}")
            # Try to handle as a legacy message for backward compatibility
            if receiver_id is not None:
                # Treat as a routed message
                logger.info(f"Treating message {original_message_id} as a legacy routed message.")
                
                # Update as routed for frontend display
                message_data["routing_status"] = "routed"
                message_for_frontend = _prepare_message_for_client(message_data, routing_status="routed")
                payload_str = json.dumps(message_for_frontend)
                await _broadcast_to_frontends(payload_str, message_type, f"Server (legacy routed)", original_message_id)
                
                # Forward to agent if valid
                if receiver_id in state.agent_statuses and state.agent_statuses[receiver_id].is_online:
                    if publish_to_agent_queue(receiver_id, message_data):
                        logger.info(f"Published legacy routed message {original_message_id} to {receiver_id}'s queue.")
                    else:
                        logger.error(f"Failed to publish legacy routed message {original_message_id} to agent {receiver_id}'s queue.")
                
    except Exception as e:
        logger.error(f"Error processing message from server input queue: {e}", exc_info=True)


async def server_input_consumer():
    """Service that consumes messages from the SERVER_INPUT_QUEUE."""
    channel = None
    logger.info(f"Starting server input consumer listening on {config.SERVER_INPUT_QUEUE}...")
    
    while not shutdown_event.is_set():
        try:
            connection = rabbitmq_utils.get_rabbitmq_connection()
            if not connection or connection.is_closed:
                logger.warning("Server input consumer: No RabbitMQ connection or connection closed. Retrying in 5s...")
                await asyncio.sleep(5)
                continue

            channel = connection.channel()
            # Ensure queue exists
            channel.queue_declare(queue=config.SERVER_INPUT_QUEUE, durable=True)
            
            # Define the callback for received messages
            def callback_wrapper(ch, method, properties, body):
                try:
                    logger.debug(f"Received raw message from {config.SERVER_INPUT_QUEUE}")
                    message_data = json.loads(body.decode('utf-8'))
                    # Run the async processing in the main event loop
                    asyncio.create_task(_process_server_input_message(message_data))
                    # Acknowledge message *after* creating the task (fire-and-forget)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    logger.debug(f"Acknowledged message from {config.SERVER_INPUT_QUEUE}")
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received on {config.SERVER_INPUT_QUEUE}: {body[:100]}...")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                except Exception as e:
                    logger.exception(f"Error in callback_wrapper for {config.SERVER_INPUT_QUEUE}: {e}")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
            # Start consuming
            channel.basic_consume(queue=config.SERVER_INPUT_QUEUE, on_message_callback=callback_wrapper, auto_ack=False)
            logger.info(f"Server input consumer started listening on {config.SERVER_INPUT_QUEUE}")
            
            # Keep consuming using process_data_events
            while not shutdown_event.is_set() and connection.is_open:
                try:
                    connection.process_data_events(time_limit=1)
                    await asyncio.sleep(0.1)  # Yield to allow other tasks to run
                except pika.exceptions.ConnectionClosedByBroker:
                    logger.warning("Server input consumer: Connection closed by broker. Reconnecting...")
                    break
                except pika.exceptions.AMQPConnectionError:
                    logger.warning("Server input consumer: AMQP connection error. Reconnecting...")
                    break
                except Exception as e:
                    logger.error(f"Unexpected error in server input consumer: {e}")
                    await asyncio.sleep(1)  # Wait before retrying
                    
        except pika.exceptions.ChannelClosedByBroker:
            logger.warning("Server input consumer: Channel closed by broker. Reconnecting...")
            await asyncio.sleep(5)
        except pika.exceptions.AMQPConnectionError:
            logger.error("Server input consumer: AMQP Connection Error. Reconnecting...")
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("Server input consumer task cancelled.")
            break
        except Exception as e:
            logger.exception(f"Unexpected error in server input consumer: {e}")
            await asyncio.sleep(5)
        finally:
            if channel and channel.is_open:
                try:
                    channel.close()
                    logger.info("Server input consumer channel closed.")
                except Exception as close_exc:
                    logger.error(f"Error closing server input consumer channel: {close_exc}")
            
    logger.info("Server input consumer service stopped.")

# --- Periodic Status Broadcast Service --- 

async def periodic_status_broadcast():
    """Service to periodically broadcast full agent status to frontend clients."""
    logger.info("Starting periodic status broadcast service...")
    while not shutdown_event.is_set(): # Check shutdown flag
        try:
            logger.info(f"Scheduled broadcast of full agent status...")
            # Broadcast full agent status (includes online/offline)
            await agent_manager.broadcast_agent_status(force_full_update=True, target_websocket=None)
            
            # Wait for the next interval, checking for cancellation
            await asyncio.sleep(config.PERIODIC_STATUS_INTERVAL)
            
        except asyncio.CancelledError:
            logger.info("Periodic status broadcast service task cancelled.")
            break # Exit loop if cancelled
        except Exception as e:
            logger.exception(f"Error in periodic status broadcast service: {e}. Continuing after 5s...")
            await asyncio.sleep(5) # Avoid rapid failure loops

    logger.info("Periodic status broadcast service stopped.")

# --- Agent Metadata Consumer Service ---

async def agent_metadata_consumer():
    """Service that consumes messages from the AGENT_METADATA_QUEUE."""
    channel = None
    logger.info(f"Starting agent metadata consumer listening on {config.AGENT_METADATA_QUEUE}...")
    
    while not shutdown_event.is_set():
        try:
            connection = rabbitmq_utils.get_rabbitmq_connection()
            if not connection or connection.is_closed:
                logger.warning("Agent metadata consumer: No RabbitMQ connection or connection closed. Retrying in 5s...")
                await asyncio.sleep(5)
                continue

            channel = connection.channel()
            # Ensure queue exists
            channel.queue_declare(queue=config.AGENT_METADATA_QUEUE, durable=True)
            
            # Define the callback for received messages
            def callback_wrapper(ch, method, properties, body):
                try:
                    logger.debug(f"Received raw message from {config.AGENT_METADATA_QUEUE}")
                    message_data = json.loads(body.decode('utf-8'))
                    # Run the async processing in the main event loop
                    asyncio.create_task(_process_agent_metadata_message(message_data))
                    # Acknowledge message *after* creating the task (fire-and-forget)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    logger.debug(f"Acknowledged message from {config.AGENT_METADATA_QUEUE}")
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received on {config.AGENT_METADATA_QUEUE}: {body[:100]}...")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                except Exception as e:
                    logger.exception(f"Error in callback_wrapper for {config.AGENT_METADATA_QUEUE}: {e}")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
            # Start consuming
            channel.basic_consume(queue=config.AGENT_METADATA_QUEUE, on_message_callback=callback_wrapper, auto_ack=False)
            logger.info(f"Agent metadata consumer started listening on {config.AGENT_METADATA_QUEUE}")
            
            # Keep consuming using process_data_events
            while not shutdown_event.is_set() and connection.is_open:
                try:
                    connection.process_data_events(time_limit=1)
                    await asyncio.sleep(0.1)  # Yield to allow other tasks to run
                except pika.exceptions.ConnectionClosedByBroker:
                    logger.warning("Agent metadata consumer: Connection closed by broker. Reconnecting...")
                    break
                except pika.exceptions.AMQPConnectionError:
                    logger.warning("Agent metadata consumer: AMQP connection error. Reconnecting...")
                    break
                except Exception as e:
                    logger.error(f"Unexpected error in agent metadata consumer: {e}")
                    await asyncio.sleep(1)  # Wait before retrying
                    
        except pika.exceptions.ChannelClosedByBroker:
            logger.warning("Agent metadata consumer: Channel closed by broker. Reconnecting...")
            await asyncio.sleep(5)
        except pika.exceptions.AMQPConnectionError:
            logger.error("Agent metadata consumer: AMQP Connection Error. Reconnecting...")
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("Agent metadata consumer task cancelled.")
            break
        except Exception as e:
            logger.exception(f"Unexpected error in agent metadata consumer: {e}")
            await asyncio.sleep(5)
        finally:
            if channel and channel.is_open:
                try:
                    channel.close()
                    logger.info("Agent metadata consumer channel closed.")
                except Exception as close_exc:
                    logger.error(f"Error closing agent metadata consumer channel: {close_exc}")
            
    logger.info("Agent metadata consumer service stopped.")

async def _process_agent_metadata_message(message_data: dict):
    """Process a single message from the agent_metadata_queue."""
    message_type = message_data.get("message_type")
    
    if message_type == MessageType.REGISTER_BROKER:
        # Handle broker registration via RabbitMQ
        await _handle_broker_registration(message_data)
    elif message_type == MessageType.CLIENT_DISCONNECTED:
        # Handle disconnection notification
        await _handle_client_disconnected(message_data)
    else:
        logger.warning(f"Unrecognized message type in agent metadata queue: {message_type}")

async def _handle_broker_registration(message_data: dict):
    """Handle broker registration via RabbitMQ."""
    broker_name = message_data.get("broker_name", "Unknown Broker")
    broker_id = message_data.get("broker_id")
    
    if not broker_id:
        # Generate broker ID if not provided
        broker_id = f"broker_{uuid.uuid4().hex[:8]}"
    
    logger.info(f"Handling broker registration via RabbitMQ: {broker_name} (ID: {broker_id})")
    
    # Update broker status
    async with state.broker_status_lock:
        state.broker_statuses[broker_id] = {
            "is_online": True,
            "last_seen": datetime.now().isoformat()
        }
    
    # Get gRPC config for the response
    grpc_host = os.getenv("GRPC_HOST", "localhost")
    grpc_port = os.getenv("GRPC_PORT", "50051")
    
    # Create response
    response = {
        "message_type": MessageType.REGISTER_BROKER_RESPONSE,
        "status": ResponseStatus.SUCCESS,
        "broker_id": broker_id,
        "broker_name": broker_name,
        "message": "Broker registered successfully via RabbitMQ",
        "grpc_host": grpc_host,
        "grpc_port": grpc_port,
        "use_grpc_for_agent_status": True
    }
    
    # Send response to the server input queue (broker will consume from there)
    if not rabbitmq_utils.publish_to_queue(config.SERVER_INPUT_QUEUE, response):
        logger.error(f"Failed to send registration response to broker {broker_id}")
    else:
        logger.info(f"Sent registration response to broker {broker_id}")

async def _handle_client_disconnected(message_data: dict):
    """Handle client disconnection notification."""
    client_id = message_data.get("client_id")
    client_type = message_data.get("client_type", "unknown")
    
    if not client_id:
        logger.warning("Received CLIENT_DISCONNECTED message without client_id")
        return
    
    logger.info(f"Handling client disconnection via RabbitMQ: {client_id} ({client_type})")
    
    if client_id.startswith("broker_"):
        # Update broker status
        async with state.broker_status_lock:
            if client_id in state.broker_statuses:
                state.broker_statuses[client_id]["is_online"] = False
                state.broker_statuses[client_id]["last_seen"] = datetime.now().isoformat()
                logger.info(f"Marked broker {client_id} as offline due to disconnection message")

async def _handle_control_message(message_data: dict):
    """Handle new agent/system control messages (pause, deregister, reset, etc)."""
    message_type = message_data.get("message_type")
    agent_id = message_data.get("agent_id")
    logger.info(f"[CONTROL] Received control message: {message_type} agent_id={agent_id}")

    # Handle PAUSE_ALL_AGENTS
    if message_type == MessageType.PAUSE_ALL_AGENTS:
        from agent_registration_service import send_command_to_agent
        # Iterate over all online agents and send a pause command
        tasks = []
        for agent_id, status in state.agent_statuses.items():
            if status.is_online:
                # Set agent status to paused
                status.status = "paused"
                # Send a 'pause' command (type can be 'pause', content can be empty or a message)
                tasks.append(send_command_to_agent(agent_id, "pause", ""))
        if tasks:
            await asyncio.gather(*tasks)
            logger.info(f"Sent PAUSE command to {len(tasks)} agents.")
            # Broadcast updated status
            await agent_manager.broadcast_agent_status(force_full_update=True)
        else:
            logger.info("No online agents to pause.")

# --- Service Management --- 

async def start_services():
    """Creates and starts all background services."""
    logger.info("Starting background services...")
    # Ensure RabbitMQ connection is attempted before starting consumers
    if not rabbitmq_utils.get_rabbitmq_connection():
        logger.warning("Failed to establish initial RabbitMQ connection. Services depending on it might fail to start properly.")

    # Create tasks for each service
    service_tasks = [
        # Replace response_consumer with server_input_consumer
        asyncio.create_task(server_input_consumer(), name="ServerInputConsumer"),
        asyncio.create_task(periodic_status_broadcast(), name="PeriodicStatusBroadcast"),
        asyncio.create_task(agent_metadata_consumer(), name="AgentMetadataConsumer")
    ]
    logger.info(f"Started {len(service_tasks)} background services:")
    for task in service_tasks:
        logger.info(f"  - {task.get_name()}")
    # No need to await tasks here, they run in the background

async def stop_services():
    """Attempts to gracefully stop all background services."""
    logger.info("Stopping background services...")
    # Signal services to shut down
    shutdown_event.set()

    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if not tasks:
        logger.info("No background tasks found to stop.")
        # Still close RabbitMQ connection if it was opened
        rabbitmq_utils.close_rabbitmq_connection()
        return

    logger.info(f"Waiting for {len(tasks)} background tasks to complete shutdown...")
    
    # Wait for tasks to finish cancelling/shutting down
    try:
        # Give tasks time to finish gracefully
        await asyncio.wait(tasks, timeout=10.0) # Increased timeout
        logger.info("Background tasks shutdown complete.")
    except asyncio.TimeoutError:
        logger.warning("Timeout waiting for background tasks to finish shutdown. Forcing cancellation.")
        # Force cancel any remaining tasks
        for task in tasks:
            if not task.done():
                 task.cancel()
        # Wait a moment for cancellations to process
        await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"Error during service shutdown wait: {e}")

    # Close RabbitMQ connection after services are stopped
    rabbitmq_utils.close_rabbitmq_connection()
    logger.info("Background services stopped.")