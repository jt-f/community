import asyncio
import logging
import json
import pika
from datetime import datetime, timedelta
from fastapi import WebSocket # Added for _safe_send_websocket type hint

# Import shared models, config, state, and utils
from shared_models import MessageType, setup_logging
import config
import state
import rabbitmq_utils
import agent_manager
import utils

# Import the necessary publish functions explicitly
from rabbitmq_utils import publish_to_agent_queue, publish_to_broker_input_queue

# Create shutdown event for graceful service termination
shutdown_event = asyncio.Event()

# Create lock for thread-safe access to agent connections
agent_connections_lock = asyncio.Lock()

# Use the same ping interval as configured for agents
PING_INTERVAL = config.AGENT_PING_INTERVAL

logger = setup_logging(__name__)

# --- Helper Functions ---

def _prepare_message_for_client(response_data: dict, routing_status: str | None = None) -> dict:
    """Creates a copy of the response data, removes internal keys, and adds routing status."""
    message_copy = response_data.copy()
    # Remove internal RabbitMQ routing keys first
    for key in ["_broadcast", "_target_agent_id", "_client_id"]:
        message_copy.pop(key, None)
    # Add the routing status for the frontend
    if routing_status:
        message_copy["_routing_status"] = routing_status
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
        logger.info(f"Broadcasting message {message_id} from {origin_desc} to {frontend_count} frontend clients.")
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
    """Processes a single message received from the server_input_queue."""
    message_type = message_data.get("message_type")
    sender_id = message_data.get("sender_id", "unknown")
    receiver_id = message_data.get("receiver_id")
    message_id = message_data.get("message_id", "N/A")

    try:
        # --- Priority Case: Direct message from Broker (e.g., routing error) ---
        if sender_id == "BrokerService":
            logger.info(f"Received direct message ID {message_id} from BrokerService for receiver {receiver_id}.")
            routing_status = "error" # Default for broker messages
            if message_type == MessageType.ERROR and receiver_id == "Server":
                 routing_status = "routing_failed"
                 logger.warning(f"Broker reported routing failure: {message_data.get('text_payload')}")
            else:
                 logger.warning(f"Received unhandled direct message type {message_type} from BrokerService.")

            message_for_frontend = _prepare_message_for_client(message_data, routing_status=routing_status)
            payload_str = json.dumps(message_for_frontend)
            await _broadcast_to_frontends(payload_str, message_type, "Broker (status/error)",message_id)
            # Stop processing here for direct broker messages

        # --- Case 2: Message needs routing (From Agent, no specific receiver yet) ---
        elif sender_id in state.agent_statuses and receiver_id is None: # Assume None receiver means needs routing
            logger.info(f"Message ID {message_id} from agent {sender_id} requires routing (receiver_id is None).")

            # Broadcast as pending
            message_for_frontend = _prepare_message_for_client(message_data, routing_status="pending")
            payload_str = json.dumps(message_for_frontend)
            await _broadcast_to_frontends(payload_str, message_type, f"agent {sender_id} (pending)",message_id)

            # Publish to Broker
            if publish_to_broker_input_queue(message_data):
                logger.info(f"Published message ID {message_id} from agent {sender_id} to broker_input_queue.")
            else:
                logger.error(f"Failed to publish message ID {message_id} from agent {sender_id} to broker_input_queue.")

        # --- Case 3: Message has been routed (has a specific receiver_id) ---
        # This now correctly covers messages originally from agents OR frontends after broker routing.
        elif receiver_id is not None:
            logger.info(f"received routed message {message_id} on server_input_queue for final receiver {receiver_id}.")

            # Broadcast as routed
            message_for_frontend = _prepare_message_for_client(message_data, routing_status="routed")
            payload_str = json.dumps(message_for_frontend)
            # Use original sender in the broadcast origin description for clarity
            await _broadcast_to_frontends(payload_str, message_type, f"Server (routed to {receiver_id})", message_id)

            # Forward to the final agent recipient
            if receiver_id in state.agent_statuses:
                if state.agent_statuses[receiver_id].is_online:
                    if publish_to_agent_queue(receiver_id, message_data):
                        logger.info(f"Published routed message {message_id} to {receiver_id}'s queue.")
                    else:
                        logger.error(f"Failed to publish routed message {message_id} to agent {receiver_id}'s queue.")
                else:
                    logger.warning(f"Routed message ID intended for agent {receiver_id}, but agent is offline.")
                    # TODO: Maybe notify original sender? For now, just log.
            elif receiver_id == "Server":
                 # A message explicitly routed *back* to the server? Handle if necessary.
                 logger.info(f"Message {message_id} from {sender_id} was routed back to the Server. Processing not implemented.")
                 # Could process server-specific commands here.
            else:
                # Broker routed to an unknown agent ID? Should not happen ideally.
                logger.warning(f"Routed message {message_id} has unknown receiver_id: {receiver_id}. Cannot deliver.")
                logger.warning(f"Known agents: {state.agent_statuses}")
        # --- Case 4: Unhandled message (e.g., from Frontend directly? Unknown sender?) ---
        else:
            # This covers non-agent senders where receiver_id is None.
            logger.warning(f"Received unhandled message {message_id} on server_input_queue. Sender: {sender_id}, Receiver: {receiver_id}. Discarding.")

    except Exception as e:
        logger.exception(f"Error processing server_input_queue message (ID: {message_id}): {e}")


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
                    # Pass the decoded message_data directly
                    asyncio.create_task(_process_server_input_message(message_data))
                    # Acknowledge message *after* creating the task (fire-and-forget)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    logger.debug(f"Acknowledged message from {config.SERVER_INPUT_QUEUE}")
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received on {config.SERVER_INPUT_QUEUE}: {body[:100]}...") # Log truncated body
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False) # Discard invalid JSON
                except Exception as e:
                    logger.exception(f"Error in callback_wrapper for {config.SERVER_INPUT_QUEUE}: {e}")
                    # Nack without requeue to avoid poison messages
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
            # Start consuming
            channel.basic_consume(queue=config.SERVER_INPUT_QUEUE, on_message_callback=callback_wrapper, auto_ack=False) # Manual ACK
            logger.info(f"Server input consumer started listening on {config.SERVER_INPUT_QUEUE}")
            
            # Keep consuming using process_data_events
            while not shutdown_event.is_set() and connection.is_open:
                connection.process_data_events(time_limit=1) # Process events for 1 second
                await asyncio.sleep(0.1) # Yield to allow other tasks to run
                
            logger.warning("Server input consumer: Shutdown signal received or connection closed. Exiting consumption loop.")

        except pika.exceptions.ChannelClosedByBroker as e:
             logger.warning(f"Server input consumer: Channel closed by broker: {e}. Reconnecting...")
             await asyncio.sleep(5)
        except pika.exceptions.StreamLostError as e:
             logger.warning(f"Server input consumer: Stream lost error (connection closed): {e}. Reconnecting...")
             await asyncio.sleep(5)
        except pika.exceptions.AMQPConnectionError as e:
             logger.error(f"Server input consumer: AMQP Connection Error: {e}. Reconnecting...")
             await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("Server input consumer task cancelled.")
            break # Exit loop if cancelled
        except Exception as e:
            logger.exception(f"Unexpected error in server input consumer: {e}. Retrying in 5s...")
            await asyncio.sleep(5)
        finally:
            if channel and channel.is_open:
                try:
                    channel.close()
                    logger.info("Server input consumer channel closed.")
                except Exception as close_exc:
                    logger.error(f"Error closing server input consumer channel: {close_exc}")
            # Reset connection state if needed (get_rabbitmq_connection should handle this)
            rabbitmq_utils.close_rabbitmq_connection() # Ensure connection is flagged for potential reopening
            
    logger.info("Server input consumer service stopped.")

# --- Agent Ping Service --- 

async def agent_ping_service():
    """Periodically pings all connected agents to check their status."""
    while not shutdown_event.is_set():
        try:
            # Get list of current agents
            async with agent_connections_lock:
                current_agents = list(state.agent_connections.items())
            
            disconnected_agents = set()
            if not current_agents:
                logger.debug("Agent ping service: No agents connected, skipping ping cycle.")
            else:
                logger.debug(f"Agent ping service: Sending PING to {len(current_agents)} agents...")
                ping_message = json.dumps({"message_type": MessageType.PING, "timestamp": datetime.now().isoformat()})
                for agent_id, ws in current_agents:
                    client_desc = f"agent {agent_id}"
                    logger.debug(f"Pinging {client_desc}")
                    if not await _safe_send_websocket(ws, ping_message, client_desc):
                        logger.error(f"Error sending PING to agent {agent_id}, marking for disconnection.")
                        disconnected_agents.add(agent_id) # Mark agent ID for removal
            
            # Handle disconnected agents
            needs_broadcast = False
            if disconnected_agents:
                logger.info(f"Handling {len(disconnected_agents)} agents disconnected during ping.")
                # No lock needed here as handle_agent_disconnection manages its own logic if necessary
                for agent_id in disconnected_agents:
                     # Use the centralized handler which also removes from state.agent_connections if present
                    if await agent_manager.handle_agent_disconnection(agent_id):
                            needs_broadcast = True # Flag if any agent status actually changed to offline
                            logger.info(f"Agent {agent_id} marked as offline due to ping failure/send error.")
            
            # Broadcast status update if needed
            if needs_broadcast:
                logger.info("Triggering agent status broadcast via WebSocket after handling ping failures")
                # Use create_task to avoid blocking the ping service loop
                asyncio.create_task(agent_manager.broadcast_agent_status())
            
        except asyncio.CancelledError:
            logger.info("Agent ping service task cancelled.")
            break # Exit the loop if cancelled
        except Exception as e:
            logger.exception(f"Error in agent ping service: {e}")

        # Wait for next ping cycle
        try:
            await asyncio.sleep(PING_INTERVAL)
        except asyncio.CancelledError:
            logger.info("Agent ping service cancelled during sleep.")
            break

# --- Periodic Status Broadcast Service --- 

async def periodic_status_broadcast():
    """Service to periodically broadcast full agent status to frontend clients."""
    logger.info("Starting periodic status broadcast service...")
    while not shutdown_event.is_set(): # Check shutdown flag
        try:
            logger.info(f"Scheduled broadcast of full agent status...")
            # Broadcast full agent status (includes online/offline)
            await agent_manager.broadcast_agent_status(force_full_update=True)
            
            # Wait for the next interval, checking for cancellation
            await asyncio.sleep(config.PERIODIC_STATUS_INTERVAL)
            
        except asyncio.CancelledError:
            logger.info("Periodic status broadcast service task cancelled.")
            break # Exit loop if cancelled
        except Exception as e:
            logger.exception(f"Error in periodic status broadcast service: {e}. Continuing after 5s...")
            await asyncio.sleep(5) # Avoid rapid failure loops

    logger.info("Periodic status broadcast service stopped.")

# --- Server Heartbeat Service ---

async def server_heartbeat_service():
    """Service to periodically send heartbeat messages to all connected clients."""
    logger.info("Starting server heartbeat service...")
    while not shutdown_event.is_set():
        try:
            heartbeat_message = {
                "message_type": MessageType.SERVER_HEARTBEAT,
                "timestamp": datetime.now().isoformat(),
                "sender_id": "server"
            }
            
            heartbeat_str = json.dumps(heartbeat_message)
            
            # Collect clients to send to
            all_clients = []
            frontend_clients = [(ws, f"frontend {getattr(ws, 'client_id', '?')}") for ws in list(state.frontend_connections)]
            agent_clients = [(ws, f"agent {agent_id}") for agent_id, ws in list(state.agent_connections.items())]
            broker_clients = [(ws, f"broker {broker_id}") for broker_id, ws in list(state.broker_connections.items())]
            all_clients.extend(frontend_clients)
            all_clients.extend(agent_clients)
            all_clients.extend(broker_clients)

            if not all_clients:
                 logger.debug("Heartbeat: No clients connected.")
            else:
                 logger.debug(f"Sending heartbeat to {len(all_clients)} clients...")

            # Send heartbeats and collect disconnections
            disconnected_frontends = set()
            disconnected_agents = set()
            disconnected_brokers = set()

            for ws, client_desc in all_clients:
                if not await _safe_send_websocket(ws, heartbeat_str, client_desc):
                    # Determine client type based on state collections (might be imperfect if ws object is reused)
                    if ws in state.frontend_connections:
                         disconnected_frontends.add(ws)
                    else:
                         # Check agents
                         found_agent = False
                         for agent_id, agent_ws in list(state.agent_connections.items()):
                             if ws == agent_ws:
                                 disconnected_agents.add(agent_id)
                                 found_agent = True
                                 break
                         # Check brokers if not agent
                         if not found_agent:
                              for broker_id, broker_ws in list(state.broker_connections.items()):
                                  if ws == broker_ws:
                                      disconnected_brokers.add(broker_id)
                                      break
            
            # Handle disconnected clients
            if disconnected_frontends:
                state.frontend_connections -= disconnected_frontends
                logger.info(f"Removed {len(disconnected_frontends)} disconnected frontend clients during heartbeat")
            
            needs_agent_broadcast = False
            # Use agent_manager for agent disconnections
            for agent_id in disconnected_agents:
                 if await agent_manager.handle_agent_disconnection(agent_id):
                     needs_agent_broadcast = True
            
            # Handle broker disconnections (simple removal for now)
            if disconnected_brokers:
                 for broker_id in disconnected_brokers:
                     if broker_id in state.broker_connections:
                         del state.broker_connections[broker_id]
                         logger.info(f"Removed disconnected broker {broker_id} during heartbeat.")

            # Broadcast agent status if any agents were disconnected
            if needs_agent_broadcast:
                 logger.info("Triggering agent status broadcast due to heartbeat disconnections.")
                 await agent_manager.broadcast_agent_status()
            
            # Wait for next heartbeat interval
            await asyncio.sleep(10)  # Send heartbeat every 10 seconds
            
        except asyncio.CancelledError:
            logger.info("Server heartbeat service task cancelled.")
            break
        except Exception as e:
            logger.exception(f"Error in server heartbeat service: {e}")
            await asyncio.sleep(5)  # Wait a bit before retrying
    
    logger.info("Server heartbeat service stopped.")

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
        asyncio.create_task(agent_ping_service(), name="AgentPingService"),
        asyncio.create_task(periodic_status_broadcast(), name="PeriodicStatusBroadcast"),
        asyncio.create_task(server_heartbeat_service(), name="ServerHeartbeat")
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