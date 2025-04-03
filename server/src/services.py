import asyncio
import logging
import json
from datetime import datetime, timedelta

# Import shared models, config, state, and utils
from shared_models import MessageType, ChatMessage
import config
import state
import rabbitmq_utils
import agent_manager

logger = logging.getLogger(__name__)

# --- Response Consumer Service --- 

async def forward_response_to_client(response_data: dict):
    """Forward a response from the broker to the appropriate WebSocket client."""
    try:
        # Handle broadcast flag for sending to all clients
        if response_data.get("_broadcast") is True:
            # Send to all frontend clients
            disconnected_frontend = set()
            for ws in state.frontend_connections:
                try:
                    # Create a copy of the message without routing metadata
                    message_to_client = response_data.copy()
                    for key in ["_broadcast", "_target_agent_id", "_client_id"]:
                        message_to_client.pop(key, None)
                            
                    await ws.send_text(json.dumps(message_to_client))
                except Exception as e:
                    logger.error(f"Error sending broadcast to frontend client {getattr(ws, 'client_id', '?')}: {e}")
                    disconnected_frontend.add(ws)
            state.frontend_connections -= disconnected_frontend # Clean up disconnected
            
            # Send to all agents except the sender
            disconnected_agents = set()
            sender_id = response_data.get("sender_id")
            for agent_id, ws in state.agent_connections.items():
                if agent_id != sender_id:  # Don't send back to sender
                    try:
                        message_to_agent = response_data.copy()
                        for key in ["_broadcast", "_target_agent_id", "_client_id"]:
                            message_to_agent.pop(key, None)
                                
                        await ws.send_text(json.dumps(message_to_agent))
                    except Exception as e:
                        logger.error(f"Error sending broadcast to agent {agent_id}: {e}")
                        disconnected_agents.add(agent_id)
            
            # Clean up disconnected agents
            for agent_id in disconnected_agents:
                 if agent_id in state.agent_connections:
                      del state.agent_connections[agent_id]
                 agent_manager.mark_agent_offline(agent_id) # Mark as offline
            if disconnected_agents:
                await agent_manager.broadcast_agent_status() # Broadcast changes

            logger.info("Broadcast message sent to remaining clients and agents")
            return
            
        # Handle direct messages to a specific agent
        target_agent_id = response_data.get("_target_agent_id")
        if target_agent_id:
            if target_agent_id in state.agent_connections:
                agent_ws = state.agent_connections[target_agent_id]
                try:
                    message_to_agent = response_data.copy()
                    for key in ["_broadcast", "_target_agent_id", "_client_id"]:
                        message_to_agent.pop(key, None)
                    
                    await agent_ws.send_text(json.dumps(message_to_agent))
                    logger.info(f"Message forwarded to agent {target_agent_id}")
                except Exception as e:
                     logger.error(f"Error forwarding message to agent {target_agent_id}: {e}. Removing agent connection.")
                     del state.agent_connections[target_agent_id]
                     agent_manager.mark_agent_offline(target_agent_id)
                     await agent_manager.broadcast_agent_status()
            else:
                logger.warning(f"Target agent {target_agent_id} not connected, cannot deliver message: {response_data.get('message_type')}")
            return
        
        # Handle messages targeted at a specific client_id (usually original sender)
        client_id = response_data.get("client_id") or response_data.get("_client_id")
        if client_id:
            target_websocket = None
            # Check active connections (could be frontend or agent)
            for websocket in state.active_connections:
                if getattr(websocket, "client_id", None) == client_id:
                    target_websocket = websocket
                    break
            
            if target_websocket:
                try:
                    message_to_client = response_data.copy()
                    for key in ["_broadcast", "_target_agent_id", "_client_id"]:
                         message_to_client.pop(key, None)
                    
                    await target_websocket.send_text(json.dumps(message_to_client))
                    logger.info(f"Response forwarded to client {client_id}: {message_to_client.get('message_type')}")
                except Exception as e:
                    logger.error(f"Error sending response to client {client_id}: {e}. Removing connection.")
                    # Need to properly remove the connection from relevant sets/dicts
                    state.active_connections.discard(target_websocket)
                    state.frontend_connections.discard(target_websocket)
                    found_agent_id = None
                    for ag_id, ws in state.agent_connections.items():
                        if ws == target_websocket:
                            found_agent_id = ag_id
                            break
                    if found_agent_id:
                        del state.agent_connections[found_agent_id]
                        agent_manager.mark_agent_offline(found_agent_id)
                        await agent_manager.broadcast_agent_status()
                    # No need to mark broker_connection as None here, handled elsewhere
            else:
                logger.warning(f"Client {client_id} not found for response delivery: {response_data.get('message_type')}")
        else:
            # If no routing information, log it
            logger.warning(f"Received response without specific routing info (_broadcast, _target_agent_id, _client_id), cannot route: {response_data}")

    except Exception as e:
        logger.exception(f"Unexpected error in forward_response_to_client: {e}") # Use exception for full traceback


async def process_message(channel, method, properties, body):
    """Callback to process a message received from the SERVER_RESPONSE_QUEUE."""
    try:
        response_data = json.loads(body.decode('utf-8')) # Decode body
        logger.debug(f"Received response message from broker: {response_data.get('message_type', 'unknown type')}")
        
        # Handle broker explicitly requesting agent status update
        if response_data.get("message_type") == MessageType.REQUEST_AGENT_STATUS:
            logger.info("Received agent status request from broker via RabbitMQ.")
            # Send the current ACTIVE agent list via RabbitMQ
            await agent_manager.send_agent_status_to_broker() 
            # Also broadcast any recent changes via WebSocket (optional, depends on desired sync)
            # await agent_manager.broadcast_agent_status() 
        else:
            # Forward other messages to the appropriate WebSocket client
            await forward_response_to_client(response_data)
        
        # Acknowledge message processing to RabbitMQ
        channel.basic_ack(delivery_tag=method.delivery_tag)

    except json.JSONDecodeError:
        logger.error(f"Invalid JSON received from broker response queue: {body}")
        # Reject message, don't requeue bad JSON
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        logger.exception(f"Error processing message from broker response queue: {e}") # Log traceback
        # Reject message, possibly requeue depending on error?
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False) 


async def response_consumer():
    """Service that consumes messages from the SERVER_RESPONSE_QUEUE."""
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
            channel.queue_declare(queue=config.SERVER_RESPONSE_QUEUE, durable=True)
            
            # Define the callback for received messages
            def callback_wrapper(ch, method, properties, body):
                # Run the async process_message in the main event loop
                asyncio.create_task(process_message(ch, method, properties, body))
            
            channel.basic_consume(queue=config.SERVER_RESPONSE_QUEUE, on_message_callback=callback_wrapper)
            
            logger.info(f"Response consumer started listening on {config.SERVER_RESPONSE_QUEUE}")
            
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
                    if agent_id in state.agent_connections:
                        del state.agent_connections[agent_id]
                        agent_manager.mark_agent_offline(agent_id)
                        needs_broadcast = True
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
                            agent_manager.mark_agent_offline(agent_id)
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