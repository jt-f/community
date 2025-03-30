from fastapi import FastAPI, WebSocket
import asyncio
import json
import logging
import pika # Added for direct publishing
import os     # Added for RabbitMQ config
import time   # Added for retry logic
import threading

# Import shared models directly - they will always be available
from shared_models import ChatMessage, MessageType, ResponseStatus

app = FastAPI()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
INCOMING_QUEUE = 'incoming_messages_queue'
BROKER_CONTROL_QUEUE = 'broker_control_queue'  # New queue for control messages to broker
SERVER_RESPONSE_QUEUE = 'server_response_queue'  # Queue for broker responses to server

# Store active websocket connections
active_connections = {}  # client_id -> websocket

def get_rabbitmq_connection():
    """Establishes a connection to RabbitMQ with retry logic."""
    # Simplified connection logic for the server part
    credentials = pika.PlainCredentials('guest', 'guest')
    parameters = pika.ConnectionParameters(RABBITMQ_HOST, RABBITMQ_PORT, '/', credentials)
    retries = 5
    while retries > 0:
        try:
            connection = pika.BlockingConnection(parameters)
            logging.info("Server successfully connected to RabbitMQ.")
            return connection
        except pika.exceptions.AMQPConnectionError as e:
            logging.warning(f"Server failed to connect to RabbitMQ: {e}. Retrying in 5 seconds... ({retries} retries left)")
            retries -= 1
            time.sleep(5)
    logging.error("Server could not connect to RabbitMQ after multiple retries.")
    return None

def publish_to_queue(queue_name, message_data):
    """Publishes a message to the specified queue."""
    connection = None
    channel = None
    try:
        connection = get_rabbitmq_connection()
        if not connection or connection.is_closed:
            logging.error(f"Failed to establish RabbitMQ connection for publishing to {queue_name}.")
            return False

        channel = connection.channel()
        channel.queue_declare(queue=queue_name, durable=True)
        channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=json.dumps(message_data),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        logging.info(f"Message published to {queue_name}.")
        return True
    except Exception as e:
        logging.error(f"Error publishing message to {queue_name}: {e}", exc_info=True)
        return False
    finally:
        if channel and channel.is_open:
            channel.close()
        if connection and connection.is_open:
            connection.close()

def publish_to_incoming_queue(message: ChatMessage):
    """Publishes a message directly to the incoming queue."""
    try:
        if publish_to_queue(INCOMING_QUEUE, message.dict()):
            logging.info(f"Message {message.message_id} published to {INCOMING_QUEUE}.")
            return True
        return False
    except Exception as e:
        logging.error(f"Error publishing message {message.message_id} to {INCOMING_QUEUE}: {e}", exc_info=True)
        return False

async def forward_response_to_client(response_data):
    """Forward a response from broker to the appropriate client."""
    client_id = response_data.get("client_id")
    
    # Remove internal routing info before sending to client
    if "_client_id" in response_data:
        del response_data["_client_id"]
    
    if client_id and client_id in active_connections:
        websocket = active_connections[client_id]
        try:
            await websocket.send_text(json.dumps(response_data))
            logging.info(f"Response forwarded to client {client_id}")
        except Exception as e:
            logging.error(f"Error forwarding response to client {client_id}: {e}")
    else:
        logging.warning(f"Cannot forward response: client {client_id} not found or not connected")

def start_response_consumer():
    """Consumes messages from the server response queue in a separate thread."""
    connection = None
    channel = None
    
    try:
        connection = get_rabbitmq_connection()
        if not connection:
            logging.error("Failed to establish RabbitMQ connection for response consumer")
            return
            
        channel = connection.channel()
        channel.queue_declare(queue=SERVER_RESPONSE_QUEUE, durable=True)
        
        logging.info(f"Started listening on {SERVER_RESPONSE_QUEUE} for broker responses")
        
        def process_response(ch, method, properties, body):
            try:
                response_data = json.loads(body)
                logging.info(f"Received response from broker")
                
                # Use asyncio to forward to the appropriate client
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(forward_response_to_client(response_data))
                
                # Acknowledge the message
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
            except json.JSONDecodeError:
                logging.error(f"Invalid JSON in response: {body}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            except Exception as e:
                logging.error(f"Error processing response: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        # Set up consumer
        channel.basic_consume(queue=SERVER_RESPONSE_QUEUE, on_message_callback=process_response)
        
        # Start consuming
        channel.start_consuming()
        
    except Exception as e:
        logging.error(f"Error in response consumer: {e}")
    finally:
        if channel and channel.is_open:
            channel.close()
        if connection and connection.is_open:
            connection.close()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = f"client_{websocket.client.host}_{websocket.client.port}"
    logging.info(f"WebSocket connection accepted from {client_id}")
    
    # Store websocket reference for reply
    active_connections[client_id] = websocket
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                # Parse the incoming message and check its type
                message_data = json.loads(data)
                message_type = message_data.get("message_type")
                
                # Handle different message types
                if message_type == MessageType.REGISTER_AGENT:
                    # Forward registration message to broker
                    logging.info(f"Forwarding agent registration request to broker")
                    
                    # Add WebSocket connection info to track which client sent this
                    message_data["_client_id"] = client_id
                    
                    # Publish to broker control queue
                    if publish_to_queue(BROKER_CONTROL_QUEUE, message_data):
                        logging.info(f"Registration request forwarded to broker")
                    else:
                        # If publishing fails, send error response back to client
                        error_response = {
                            "message_type": MessageType.REGISTER_AGENT_RESPONSE,
                            "status": ResponseStatus.ERROR,
                            "agent_id": message_data.get("agent_id", "unknown"),
                            "message": "Failed to forward registration request to broker"
                        }
                        await websocket.send_text(json.dumps(error_response))
                
                elif message_type in [MessageType.TEXT, MessageType.REPLY, MessageType.SYSTEM]:
                    # These are regular chat messages that should go to the queue
                    try:
                        incoming_message = ChatMessage(**message_data)
                        logging.info(f"Received message {incoming_message.message_id} from {incoming_message.sender_id}")
                        
                        # Publish to appropriate queue
                        publish_to_incoming_queue(incoming_message)
                            
                    except Exception as e:
                        logging.error(f"Error processing chat message: {e}")
                        error_message = ChatMessage.create(
                            sender_id="server", 
                            receiver_id=message_data.get("sender_id", "unknown"),
                            text_payload=f"Error processing message: {str(e)}", 
                            message_type=MessageType.ERROR
                        )
                        await websocket.send_text(json.dumps(error_message.dict()))
                
                else:
                    # Unhandled message type
                    logging.warning(f"Received unhandled message type: {message_type}")
                    error_message = ChatMessage.create(
                        sender_id="server", 
                        receiver_id=message_data.get("sender_id", "unknown"),
                        text_payload=f"Unsupported message type: {message_type}", 
                        message_type=MessageType.ERROR
                    )
                    await websocket.send_text(json.dumps(error_message.dict()))

            except json.JSONDecodeError:
                logging.error(f"Invalid JSON received from {client_id}: {data}")
                error_message = ChatMessage.create(
                    sender_id="server", receiver_id="unknown",
                    text_payload="Invalid message format received.", message_type=MessageType.ERROR
                )
                await websocket.send_text(json.dumps(error_message.dict()))
            except Exception as e:
                logging.error(f"Error processing message from {client_id}: {e}", exc_info=True)
                error_message = ChatMessage.create(
                    sender_id="server", receiver_id="unknown",
                    text_payload="An error occurred while processing your message.", message_type=MessageType.ERROR
                )
                if not websocket.client_state.name == "DISCONNECTED": # Check state correctly
                    await websocket.send_text(json.dumps(error_message.dict()))

    except Exception as e:
        logging.warning(f"WebSocket disconnected or error occurred for {client_id}: {e}")
    finally:
        # Clean up
        if client_id in active_connections:
            del active_connections[client_id]
            
        # Also notify broker about disconnection if needed
        disconnection_message = {
            "message_type": MessageType.CLIENT_DISCONNECTED,
            "client_id": client_id
        }
        publish_to_queue(BROKER_CONTROL_QUEUE, disconnection_message)
        
        logging.info(f"WebSocket connection closed for {client_id}")


if __name__ == "__main__":
    import uvicorn
    print("Starting FastAPI WebSocket server. Ensure RabbitMQ is running.")
    
    # Start response consumer thread
    response_thread = threading.Thread(target=start_response_consumer, daemon=True)
    response_thread.start()
    logging.info("Broker response consumer thread started")
    
    # Create the broker control queue if it doesn't exist
    connection = get_rabbitmq_connection()
    if connection:
        try:
            channel = connection.channel()
            channel.queue_declare(queue=BROKER_CONTROL_QUEUE, durable=True)
            logging.info(f"Broker control queue {BROKER_CONTROL_QUEUE} declared.")
            
            # Also create server response queue
            channel.queue_declare(queue=SERVER_RESPONSE_QUEUE, durable=True)
            logging.info(f"Server response queue {SERVER_RESPONSE_QUEUE} declared.")
        except Exception as e:
            logging.error(f"Error setting up queues: {e}")
        finally:
            if connection.is_open:
                connection.close()
    
    uvicorn.run("server:app", host="localhost", port=8765, reload=True)