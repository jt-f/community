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

logger = logging.getLogger(__name__)

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
        # Iterate over a copy in case the set is modified during iteration
        for fe_ws in list(state.frontend_connections):
            fe_client_desc = f"frontend client {getattr(fe_ws, 'client_id', '?')}"
            if not await _safe_send_websocket(fe_ws, payload_str, fe_client_desc):
                disconnected_frontend.add(fe_ws)
        # Clean up disconnected frontends immediately
        if disconnected_frontend:
            state.frontend_connections -= disconnected_frontend
            logger.info(f"Removed {len(disconnected_frontend)} disconnected frontend clients during broadcast.")

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
    """Forward a response from the broker to the appropriate WebSocket client(s).

    Also broadcasts chat messages (TEXT, REPLY, SYSTEM) to all frontends.
    """
    # Prepare the message payload once (without routing keys)
    message_to_send = _prepare_message_for_client(response_data)
    payload_str = json.dumps(message_to_send)
    needs_agent_status_broadcast = False
    message_type_str = response_data.get("message_type", "unknown type")

    try:
        # --- Broadcast Chat Messages to Frontends ---
        # Check if it's a chat message type and not already a broadcast request
        is_chat_message = False
        try:
            # Check against enum values directly
            message_type_enum = MessageType(message_type_str)
            if message_type_enum in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
                is_chat_message = True
        except ValueError:
            pass # Not a valid MessageType enum member, definitely not a chat message we handle here

        if is_chat_message and response_data.get("_broadcast") is not True:
            logger.debug(f"Broadcasting incoming chat message ({message_type_str}) from broker to frontends.")
            await _broadcast_to_frontends(payload_str, message_type_str, "broker (incoming chat)")

        # --- Original Routing Logic ---
        # Determine routing and call appropriate handler
        if response_data.get("_broadcast") is True:
            # _handle_broadcast already includes frontend broadcast, no need to do it twice
            needs_agent_status_broadcast = await _handle_broadcast(payload_str, response_data)
        elif target_agent_id := response_data.get("_target_agent_id"):
            needs_agent_status_broadcast = await _handle_direct_to_agent(payload_str, response_data, target_agent_id)
        elif client_id := response_data.get("_client_id"):
            needs_agent_status_broadcast = await _handle_direct_to_client(payload_str, response_data, client_id)
        else:
            # If no routing information, log it
            logger.warning(f"Received response without specific routing info (_broadcast, _target_agent_id, _client_id), cannot route: {response_data}")

        # --- Final Step: Broadcast status if needed ---
        if needs_agent_status_broadcast:
             logger.info("Triggering agent status broadcast after handling disconnections or agent-specific actions.")
             await agent_manager.broadcast_agent_status()

    except Exception as e:
        logger.exception(f"Unexpected error in forward_response_to_client processing message type {message_type_str}: {e}")

async def process_message(channel, method, properties, body):
    """Callback to process a message received from the BROKER_OUTPUT_QUEUE."""
    try:
        response_data = json.loads(body.decode('utf-8')) # Decode body
        logger.info(f"Received response message from broker: {response_data.get('message_type', 'unknown type')}")
        
        # Forward other messages to the appropriate WebSocket client
        await forward_response_to_client(response_data)
        
        # Acknowledge message processing to RabbitMQ
        channel.basic_ack(delivery_tag=method.delivery_tag)

    except json.JSONDecodeError:
        logger.error(f"Invalid JSON received from broker output queue: {body}")
        # Reject message, don't requeue bad JSON
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        logger.exception(f"Error processing message from broker output queue: {e}") # Log traceback
        # Reject message, possibly requeue depending on error?
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False) 


async def response_consumer():
    """Service that consumes messages from the BROKER_OUTPUT_QUEUE."""
    logger.info("Starting response consumer service...")
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
                # Run the async process_message in the main event loop
                asyncio.create_task(process_message(ch, method, properties, body))
            
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
    """Service to periodically ping agents and mark inactive ones as offline."""
    logger.info("Starting agent ping service...")
    while True:
        try:
            current_time = datetime.now()
            agents_to_ping = list(state.agent_connections.keys()) # Ping currently connected agents
            disconnected_agents = set()

            # 1. Send PING to all connected agents
            for agent_id in agents_to_ping:
                ws = state.agent_connections.get(agent_id)
                if not ws:
                    continue # Agent disconnected between getting keys and now
                try:
                    ping_message = {
                        "message_type": MessageType.PING,
                        "timestamp": current_time.isoformat() # Use ISO format
                    }
                    await ws.send_text(json.dumps(ping_message))
                    logger.debug(f"Sent PING to agent {agent_id}")
                except Exception as e:
                    logger.error(f"Error sending PING to agent {agent_id}: {e}. Marking for disconnect.")
                    disconnected_agents.add(agent_id)
            
            # Clean up agents that failed ping send
            if disconnected_agents:
                needs_broadcast = False
                for agent_id in disconnected_agents:
                    # Use the centralized handler
                    if await agent_manager.handle_agent_disconnection(agent_id):
                         needs_broadcast = True # Set flag if any disconnect was handled
                if needs_broadcast:
                    await agent_manager.broadcast_agent_status()

            # 2. Check for agents that haven't responded (based on last_seen)
            agents_marked_offline = set()
            # Iterate over a copy of agent_statuses items
            for agent_id, status in list(state.agent_statuses.items()):
                 # Only check agents that are supposed to be online
                 if status.is_online:
                    try:
                        last_seen_time = datetime.fromisoformat(status.last_seen)
                        time_diff = (current_time - last_seen_time).total_seconds()
                        
                        if time_diff > config.AGENT_INACTIVITY_TIMEOUT:
                            logger.warning(f"Agent {status.agent_name} ({agent_id}) timed out (last seen {time_diff:.1f}s ago). Marking offline.")
                            # Use centralized handler (will mark offline and remove connection)
                            await agent_manager.handle_agent_disconnection(agent_id)
                            agents_marked_offline.add(agent_id)
                            # Also remove from active connections if still present
                            if agent_id in state.agent_connections:
                                 logger.warning(f"Removing timed-out agent {agent_id} from active connections.")
                                 # Attempt to close websocket gracefully?
                                 try: await state.agent_connections[agent_id].close(code=1011, reason="Inactivity timeout") 
                                 except: pass
                                 del state.agent_connections[agent_id]
                                 
                    except ValueError:
                         logger.error(f"Invalid last_seen format for agent {agent_id}: {status.last_seen}")
                    except Exception as e:
                         logger.exception(f"Error checking inactivity for agent {agent_id}: {e}")
            
            # 3. Broadcast status if any agents were marked offline due to timeout
            if agents_marked_offline:
                await agent_manager.broadcast_agent_status()

            # Wait for the next cycle
            await asyncio.sleep(config.AGENT_PING_INTERVAL)
            
        except asyncio.CancelledError:
            logger.info("Agent ping service task cancelled.")
            raise # Re-raise cancellation
        except Exception as e:
            logger.exception(f"Unexpected error in agent ping service: {e}. Continuing after 5s...")
            await asyncio.sleep(5) # Avoid rapid failure loops

    logger.info("Agent ping service stopped.") # Should not happen


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
        asyncio.create_task(periodic_status_broadcast(), name="PeriodicStatusBroadcast")
    ]
    logger.info(f"Started {len(service_tasks)} background services.")
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