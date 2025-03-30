from fastapi import FastAPI, WebSocket
import asyncio
import json
import logging
import pika # Added for direct publishing
import os     # Added for RabbitMQ config
import time   # Added for retry logic
from shared_models import ChatMessage, MessageType

app = FastAPI()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
INCOMING_QUEUE = 'incoming_messages_queue'

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

def publish_to_incoming_queue(message: ChatMessage):
    """Publishes a message directly to the incoming queue."""
    connection = None
    channel = None
    try:
        connection = get_rabbitmq_connection()
        if not connection or connection.is_closed:
            logging.error("Failed to establish RabbitMQ connection for publishing.")
            # Handle error appropriately - maybe store message for later?
            return

        channel = connection.channel()
        channel.queue_declare(queue=INCOMING_QUEUE, durable=True)
        channel.basic_publish(
            exchange='',
            routing_key=INCOMING_QUEUE,
            body=message.json(),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        logging.info(f"Message {message.message_id} published to {INCOMING_QUEUE}.")
    except Exception as e:
        logging.error(f"Error publishing message {message.message_id} to {INCOMING_QUEUE}: {e}", exc_info=True)
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
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
                incoming_message = ChatMessage(**message_data)
                logging.info(f"Received message {incoming_message.message_id} from {incoming_message.sender_id}")

                # Publish to the central incoming queue
                publish_to_incoming_queue(incoming_message)

                # Optional: Send acknowledgement back to client immediately
                # ack_message = ChatMessage.create(...)
                # await websocket.send_text(ack_message.json())

            except json.JSONDecodeError:
                logging.error(f"Invalid JSON received from {client_id}: {data}")
                error_message = ChatMessage.create(
                    sender_id="server", receiver_id="unknown",
                    text_payload="Invalid message format received.", message_type=MessageType.ERROR
                )
                await websocket.send_text(error_message.json())
            except Exception as e:
                logging.error(f"Error processing message from {client_id}: {e}", exc_info=True)
                error_message = ChatMessage.create(
                    sender_id="server", receiver_id="unknown",
                    text_payload="An error occurred while processing your message.", message_type=MessageType.ERROR
                )
                if not websocket.client_state.name == "DISCONNECTED": # Check state correctly
                    await websocket.send_text(error_message.json())

    except Exception as e:
        logging.warning(f"WebSocket disconnected or error occurred for {client_id}: {e}")
    finally:
        logging.info(f"WebSocket connection closed for {client_id}")


if __name__ == "__main__":
    import uvicorn
    print("Starting FastAPI WebSocket server. Ensure RabbitMQ is running.")
    uvicorn.run("server:app", host="localhost", port=8765, reload=True) 