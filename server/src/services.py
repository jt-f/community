import asyncio
import logging
import json
import pika
from datetime import datetime, timedelta
from fastapi import WebSocket # Added for _safe_send_websocket type hint

# Import shared models, config, state, and utils
from shared_models import MessageType, ChatMessage
import config
import state
import rabbitmq_utils
import agent_manager
# No longer need to import websocket_handler

# Import the publish_to_agent_queue function
from rabbitmq_utils import publish_to_agent_queue

# Create shutdown event for graceful service termination
shutdown_event = asyncio.Event()

# Create lock for thread-safe access to agent connections
agent_connections_lock = asyncio.Lock()

# Use the same ping interval as configured for agents
PING_INTERVAL = config.AGENT_PING_INTERVAL


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("services")

# --- Helper Functions ---

def _prepare_message_for_client(response_data: dict) -> dict:
    """Creates a copy of the response data dictionary removing internal routing keys."""
    message_copy = response_data.copy()
    for key in ["_broadcast", "_target_agent_id", "_client_id"]:
        message_copy.pop(key, None) # Use pop with None to avoid KeyError if key absent
    return message_copy

# Re-added _safe_send_websocket as it's needed for frontend broadcasting
async def _safe_send_websocket(ws: WebSocket, payload_str: str, client_desc: str) -> bool:
    """Sends data to a WebSocket, handling exceptions and logging.

    Args:
        ws: The WebSocket connection object.
        payload_str: The JSON string payload to send.
        client_desc: A description of the client (e.g., client_id, agent_id) for logging.

    Returns:
        True if send was successful, False otherwise.
    """
    try:
        # Don't check client_state since FastAPI WebSocket objects actually
        # use a different attribute that's not directly accessible
        await ws.send_text(payload_str)
        logger.debug(f"Successfully sent message to {client_desc}")
        return True
    except Exception as e:
        # Catch WebSocketDisconnect, ConnectionClosedOK, ConnectionClosedError, etc.
        logger.error(f"Error sending message to {client_desc}: {e}. Connection assumed lost.")
        return False

# --- Response Consumer Service ---

async def _broadcast_to_frontends(payload_str: str, message_type: str, origin_desc: str = "broker"):
    """Helper to broadcast a message payload to all connected frontends."""
    disconnected_frontend = set()
    frontend_count = len(state.frontend_connections)
    if frontend_count > 0:
        logger.info(f"Broadcasting {message_type} from {origin_desc} to {frontend_count} frontend clients.")
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

async def _handle_broadcast(payload_str: str, response_data: dict) -> bool:
    """Handles broadcasting a message to all connected clients and agents."""
    # This function handles broadcasting to frontends, agents (and the broker implicitly if connected)
    needs_agent_status_broadcast = False
    message_type = response_data.get("message_type", "unknown type")
    logger.info(f"Handling broadcast request for message type {message_type}...")

    # --- Send to all frontend clients (using the helper) ---
    await _broadcast_to_frontends(payload_str, message_type, "broker (broadcast request)")

    # --- Send to all agents except the sender ---
    disconnected_agents = set()
    sender_id = response_data.get("sender_id")
    # Iterate over a copy of items in case the dict is modified
    for agent_id, ws in list(state.agent_connections.items()):
        if agent_id != sender_id:
            client_desc = f"agent {agent_id}"
            if not await _safe_send_websocket(ws, payload_str, client_desc):
                disconnected_agents.add(agent_id)

    # --- Clean up disconnected agents ---
    if disconnected_agents:
        processed_disconnects = False
        for agent_id in disconnected_agents:
            # Use the centralized handler
            if await agent_manager.handle_agent_disconnection(agent_id):
                 processed_disconnects = True
        if processed_disconnects:
             needs_agent_status_broadcast = True # Trigger broadcast if any agent was actually disconnected

    logger.debug(f"Broker broadcast request complete.")
    return needs_agent_status_broadcast


async def _handle_direct_to_agent(payload_str: str, response_data: dict, target_agent_id: str) -> bool:
    """Handles sending a message directly to a specific agent."""
    needs_agent_status_broadcast = False
    message_type = response_data.get("message_type", "unknown type")

    if target_agent_id in state.agent_connections:
        agent_ws = state.agent_connections[target_agent_id]
        client_desc = f"target agent {target_agent_id}"
        if not await _safe_send_websocket(agent_ws, payload_str, client_desc):
            # Send failed, clean up agent using the centralized handler
            logger.warning(f"Send to agent {target_agent_id} failed. Handling disconnection.")
            # The handler returns true if a change was made, signaling a need for broadcast
            needs_agent_status_broadcast = await agent_manager.handle_agent_disconnection(target_agent_id)
        else:
            logger.info(f"Message type {message_type} forwarded to agent {target_agent_id}")
    else:
        logger.warning(f"Target agent {target_agent_id} not connected, cannot deliver message: {message_type}")

    return needs_agent_status_broadcast


async def _handle_direct_to_client(payload_str: str, response_data: dict, client_id: str) -> bool:
    """Handles sending a message directly to a specific client ID."""
    needs_agent_status_broadcast = False
    message_type = response_data.get("message_type", "unknown type")
    target_websocket = None

    # --- Find the target websocket ---
    # Check active connections (could be frontend or agent)
    logger.debug(f"Attempting to find websocket for client_id: {client_id}")
    for websocket in state.active_connections:
        if getattr(websocket, "client_id", None) == client_id:
            target_websocket = websocket
            logger.debug(f"Found target websocket for {client_id}: {getattr(target_websocket, 'connection_type', '?')}")
            break

    # --- Send or handle disconnection ---
    if target_websocket:
        client_desc = f"client {client_id} ({getattr(target_websocket, 'connection_type', '?')})"
        logger.debug(f"Attempting to send {message_type} message to {client_desc}")
        send_successful = await _safe_send_websocket(target_websocket, payload_str, client_desc)
        if not send_successful:
            # Send failed, remove the connection comprehensively
            logger.warning(f"Send failed. Removing connection for client {client_id}.")
            state.active_connections.discard(target_websocket)
            state.frontend_connections.discard(target_websocket)
            found_agent_id = None
            # Iterate over copy for safe deletion
            for ag_id, ws in list(state.agent_connections.items()):
                if ws == target_websocket:
                    found_agent_id = ag_id
                    break
            if found_agent_id:
                logger.warning(f"Send to client {client_id} (agent {found_agent_id}) failed. Handling disconnection.")
                # Use centralized handler; it returns true if a change was made
                needs_agent_status_broadcast = await agent_manager.handle_agent_disconnection(found_agent_id)
        else:
            logger.info(f"Response type {message_type} forwarded to client {client_id}")
    else:
        logger.warning(f"Client {client_id} not found for response delivery: {message_type}")

    return needs_agent_status_broadcast


async def forward_response_to_client(response_data: dict):
    """Forward a response from the broker to the appropriate destination.
    
    For messages with a receiver_id that matches an agent,
    routes to that agent's queue for message processing.

    ALL messages are broadcast to all frontends for monitoring,
    regardless of message type.
    """
    # Prepare the message payload once (without internal routing keys)
    logger.info(f"Forward response to client: {response_data}")
    message_to_send = _prepare_message_for_client(response_data)
    
    # Special handling for error messages coming from the broker
    if message_to_send.get("message_type") == MessageType.ERROR and message_to_send.get("sender_id") == "BrokerService":
        original_client_id = response_data.get("_client_id")
        if original_client_id:
            # Update the receiver_id to target the original client that sent the message
            message_to_send["receiver_id"] = original_client_id
            logger.info(f"Redirecting error message to original sender: {original_client_id}")
    
    payload_str = json.dumps(message_to_send)
    needs_agent_status_broadcast = False
    message_type_str = response_data.get("message_type", "unknown type")
    receiver_id = message_to_send.get("receiver_id")  # Use the potentially modified receiver_id
    sender_id = response_data.get("sender_id", "unknown")

    try:
        # --- Step 1: ALWAYS Broadcast Messages to ALL Frontends via WebSocket ---
        # This happens for ALL message types now, not just chat messages
        logger.info(f"Broadcasting message type={message_type_str} from {sender_id} to all frontends")
        await _broadcast_to_frontends(payload_str, message_type_str, "message monitoring")

        # --- Step 2: Route the message based on receiver_id ---
        # If receiver is an agent, publish to that agent's queue for processing
        if receiver_id and receiver_id in state.agent_statuses and state.agent_statuses[receiver_id].is_online:
            # Use the helper function to publish to the agent's queue
            if publish_to_agent_queue(receiver_id, response_data):
                logger.info(f"Routed message from {sender_id} to agent {receiver_id}'s queue")
            else:
                logger.error(f"Failed to route message to agent {receiver_id}'s queue")
        
        # Handle error responses or control messages
        elif message_type_str == MessageType.ERROR:
            # Error messages from broker, route back to original sender if client_id exists
            if client_id := response_data.get("_client_id"):
                logger.info(f"Routing error message to client {client_id} via WebSocket")
                needs_agent_status_broadcast = await _handle_direct_to_client(payload_str, response_data, client_id)
            else:
                # Just log the error if no client to send to
                logger.warning(f"Error message with no client_id: {response_data.get('text_payload', 'No details')}")
        
        # For non-agent receivers (like responses to frontends)
        elif receiver_id == "server" or (receiver_id and receiver_id not in state.agent_statuses):
            # Potential direct message to a frontend client
            if client_id := response_data.get("_client_id"):
                logger.info(f"Routing message to frontend client {client_id} via WebSocket")
                needs_agent_status_broadcast = await _handle_direct_to_client(payload_str, response_data, client_id)
            else:
                # No specific client to send to, log warning
                logger.warning(f"Message for receiver {receiver_id} has no client_id routing information")
        else:
            # If no valid receiver found, log warning
            logger.warning(f"Received message without valid routing info, cannot route: type={message_type_str}, receiver={receiver_id}")

        # --- Step 3: Broadcast status updates if needed ---
        if needs_agent_status_broadcast:
             logger.info("Triggering agent status broadcast via WebSocket after handling disconnections")
             await agent_manager.broadcast_agent_status()

    except Exception as e:
        logger.exception(f"Unexpected error routing message type {message_type_str}: {e}")

async def process_message(message_data):
    """Process messages received from the broker_output_queue."""
    try:
        message_type = message_data.get("message_type")
        sender_id = message_data.get("sender_id", "unknown")
        receiver_id = message_data.get("receiver_id")
        
        logger.info(f"Processing message from {sender_id} with type {message_type}")
        
        # Handle different message types
        # REMOVED Handling for REQUEST_AGENT_STATUS from queue
        # if message_type == MessageType.REQUEST_AGENT_STATUS:
        #     ...
        
        # If this is a message intended for an agent
        if receiver_id and receiver_id in state.agent_statuses:
            # The message has a specific receiver, check if it's an agent
            if state.agent_statuses[receiver_id].is_online:
                # Agent is online, publish to their queue
                if publish_to_agent_queue(receiver_id, message_data):
                    logger.info(f"Published message to agent {receiver_id}'s queue")
                else:
                    logger.error(f"Failed to publish message to agent {receiver_id}'s queue")
                
                # If this is a chat message, also broadcast to frontends for monitoring
                if message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
                    logger.debug(f"Broadcasting {message_type} message to frontends for monitoring")
                    await _broadcast_to_frontends(json.dumps(message_data), message_type, f"agent {receiver_id}")
            else:
                logger.warning(f"Message for agent {receiver_id}, but agent is offline")
                # Send error back to sender
                error_response = {
                    "message_type": MessageType.ERROR,
                    "sender_id": "server",
                    "receiver_id": sender_id,
                    "text_payload": f"Agent {receiver_id} is offline. Message could not be delivered."
                }
                await forward_response_to_client(error_response)
        else:
            # Otherwise, broadcast message to all frontends
            await forward_response_to_client(message_data)
    except Exception as e:
        logger.error(f"Error processing message from broker_output_queue: {e}")
        logger.exception(e)


async def response_consumer():
    """Service that consumes messages from the BROKER_OUTPUT_QUEUE."""
    channel = None
    while True:
        try:
            connection = rabbitmq_utils.get_rabbitmq_connection()
            if not connection:
                logger.warning("Response consumer: No RabbitMQ connection. Retrying in 5s...")
                await asyncio.sleep(5)
                continue

            channel = connection.channel()
            channel.queue_declare(queue=config.BROKER_OUTPUT_QUEUE, durable=True)
            
            # Define the callback for received messages
            def callback_wrapper(ch, method, properties, body):
                logger.info(f"Received message from broker_output_queue: {body}")
                # Run the async process_message in the main event loop
                asyncio.create_task(process_message(json.loads(body.decode('utf-8'))))
            
            channel.basic_consume(queue=config.BROKER_OUTPUT_QUEUE, on_message_callback=callback_wrapper)
            
            logger.info(f"Response consumer started listening on {config.BROKER_OUTPUT_QUEUE}")
            
            # Keep consuming while connection is open
            while state.rabbitmq_connection and state.rabbitmq_connection.is_open:
                # Process RabbitMQ events without blocking the asyncio loop
                rabbitmq_utils.process_rabbitmq_events()
                await asyncio.sleep(0.1) # Yield control to asyncio loop
                
            logger.warning("Response consumer: RabbitMQ connection lost or closed. Attempting to reconnect...")
            # Connection lost, loop will retry

        except pika.exceptions.ChannelClosedByBroker as e:
             logger.error(f"Response consumer: Channel closed by broker: {e}. Reconnecting...")
        except pika.exceptions.AMQPConnectionError as e:
             logger.error(f"Response consumer: AMQP Connection Error: {e}. Reconnecting...")
        except Exception as e:
            logger.exception(f"Unexpected error in response consumer: {e}. Retrying in 5s...")
        finally:
            # Ensure channel is closed if it exists and connection is lost/closed
            if channel and channel.is_open:
                try: channel.close() 
                except: pass
            # Don't close the connection here, get_rabbitmq_connection handles reuse/creation
            await asyncio.sleep(5) # Wait before retrying connection/setup
            
    logger.info("Response consumer service stopped.") # Should not happen in normal operation


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
                logger.info(f"Agent ping service: Pinging {len(current_agents)} agents...")
                for agent_id, ws in current_agents:
                    try:
                        logger.debug(f"Pinging agent {agent_id}")
                        await ws.send_text(json.dumps({"message_type": MessageType.PING}))
                    except Exception as e:
                        logger.error(f"Error sending PING to agent {agent_id}: {e}")
                        disconnected_agents.add(agent_id)
            
            # Mark disconnected agents as offline
            needs_broadcast = False
            if disconnected_agents:
                async with agent_connections_lock:
                    for agent_id in disconnected_agents:
                        # Use the centralized handler which also removes from state.agent_connections
                        if await agent_manager.handle_agent_disconnection(agent_id):
                            needs_broadcast = True
                            logger.info(f"Marked agent {agent_id} as offline due to ping failure")
            
            # Broadcast status update if needed
            if needs_broadcast:
                logger.info("Triggering agent status broadcast via WebSocket after handling ping failures")
                asyncio.create_task(agent_manager.broadcast_agent_status())
            
        except asyncio.CancelledError:
            logger.info("Agent ping service task cancelled.")
            break # Exit the loop if cancelled
        except Exception as e:
            logger.error(f"Error in agent ping service: {e}")

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
    while True:
        try:
            logger.debug(f"Broadcasting full agent status periodically.")
            # Broadcast full agent status (includes online/offline)
            await agent_manager.broadcast_agent_status(force_full_update=True)
            
            # Wait for the next interval
            await asyncio.sleep(config.PERIODIC_STATUS_INTERVAL)
            
        except asyncio.CancelledError:
            logger.info("Periodic status broadcast service task cancelled.")
            raise # Re-raise cancellation
        except Exception as e:
            logger.exception(f"Error in periodic status broadcast service: {e}. Continuing after 5s...")
            await asyncio.sleep(5) # Avoid rapid failure loops

    logger.info("Periodic status broadcast service stopped.") # Should not happen


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
            
            # Count clients
            frontend_count = len(state.frontend_connections)
            agent_count = len(state.agent_connections)
            broker_count = len(state.broker_connections)
            
            logger.debug(f"Sending heartbeat to {frontend_count} frontends, {agent_count} agents, {broker_count} brokers")
            
            # Send to all frontends
            disconnected_frontends = set()
            for fe_ws in list(state.frontend_connections):
                fe_client_id = getattr(fe_ws, 'client_id', '?')
                if not await _safe_send_websocket(fe_ws, heartbeat_str, f"frontend {fe_client_id}"):
                    disconnected_frontends.add(fe_ws)
            
            # Send to all agents
            disconnected_agents = set()
            for agent_id, agent_ws in list(state.agent_connections.items()):
                if not await _safe_send_websocket(agent_ws, heartbeat_str, f"agent {agent_id}"):
                    disconnected_agents.add(agent_id)
            
            # Send to all brokers
            disconnected_brokers = set()
            for broker_id, broker_ws in list(state.broker_connections.items()):
                if not await _safe_send_websocket(broker_ws, heartbeat_str, f"broker {broker_id}"):
                    disconnected_brokers.add(broker_id)
            
            # Handle disconnected clients
            if disconnected_frontends:
                state.frontend_connections -= disconnected_frontends
                logger.info(f"Removed {len(disconnected_frontends)} disconnected frontend clients during heartbeat")
            
            async with agent_connections_lock:
                for agent_id in disconnected_agents:
                    if agent_id in state.agent_connections:
                        del state.agent_connections[agent_id]
                    agent_manager.mark_agent_offline(agent_id)
                
                for broker_id in disconnected_brokers:
                    if broker_id in state.broker_connections:
                        del state.broker_connections[broker_id]
            
            # Broadcast agent status if any agents were disconnected
            if disconnected_agents:
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
        # Decide if you want to proceed or raise an error

    # Create tasks for each service
    service_tasks = [
        asyncio.create_task(response_consumer(), name="ResponseConsumer"),
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
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if not tasks:
        logger.info("No background tasks found to stop.")
        return

    logger.info(f"Cancelling {len(tasks)} background tasks...")
    for task in tasks:
        task.cancel()
    
    # Wait for tasks to finish cancelling
    try:
        # Wait for all tasks to complete cancellation, with a timeout
        await asyncio.wait(tasks, timeout=5.0)
        logger.info("Background tasks cancellation complete.")
    except asyncio.TimeoutError:
        logger.warning("Timeout waiting for background tasks to cancel.")
    except Exception as e:
        logger.error(f"Error during service cancellation: {e}")

    # Close RabbitMQ connection after services are stopped
    rabbitmq_utils.close_rabbitmq_connection()
    logger.info("Background services stopped.") 