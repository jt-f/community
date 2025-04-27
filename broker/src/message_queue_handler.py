# Configure pika logging first
import logging
logging.getLogger("pika").setLevel(logging.WARNING)

import os
import pika
import threading
import json
import time
import logging
from datetime import datetime
import uuid
from shared_models import MessageType, setup_logging
import asyncio

logger = setup_logging(__name__)
logger.propagate = False # Prevent messages reaching the root logger

class MessageQueueHandler:
    """
    Handles all RabbitMQ connection, queue, and message operations for the agent.
    Reads host/port from environment or config internally. Only needs a logger.
    Message processing is handled by a user-provided callback.
    """
    def __init__(self, state_update=None, message_handler=None):

        self.rabbitmq_host = os.getenv("RABBITMQ_HOST", "localhost")
        self.rabbitmq_port = int(os.getenv("RABBITMQ_PORT", "5672"))
        self.connection = None
        self.channel = None
        self.consumer_tag = None
        self.queue_name = None
        self._paused = False
        self._lock = threading.Lock()
        self._message_handler = message_handler
        self._state_update = state_update

    def connect(self, queue_name):
        """Connect to RabbitMQ, declare queue, and start consumer thread with a message handler callback."""
        try:
            logger.info(f"Attempting to connect to RabbitMQ at {self.rabbitmq_host}:{self.rabbitmq_port}")
            self.connection = pika.BlockingConnection(pika.ConnectionParameters(
                host=self.rabbitmq_host,
                port=self.rabbitmq_port,
                connection_attempts=3,
                retry_delay=5
            ))
            self.channel = self.connection.channel()
            self.queue_name = queue_name
            self.channel.queue_declare(queue=self.queue_name, durable=True)
            self._paused = False
   
            self._consumer_thread = threading.Thread(target=self._consumer_loop)
            self._consumer_thread.daemon = True
            self._consumer_thread.start()
            logger.info("Connected to RabbitMQ, declared queue, and started consumer thread.")

            self._state_update('message_queue_status', 'connected')  # Pass the actual state representation
            return True
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error while connecting to RabbitMQ: {e}")
            return False

    def _consumer_loop(self):
        while True:
            with self._lock:
                if self._paused:
                    continue
            try:
                for method, properties, body in self.channel.consume(self.queue_name, inactivity_timeout=1):
                    with self._lock:
                        if self._paused:
                            break
                    if method is None:
                        continue  # Timeout, loop again
                    if self._message_handler:
                        # Decode JSON bytes to dictionary
                        try:
                            message_dict = json.loads(body)
                            # Convert gRPC message to serializable format if needed
                            if hasattr(message_dict, 'ListFields'):
                                message_dict = {k: v for k, v in message_dict.ListFields()}
                            # Handle async message handler
                            if asyncio.iscoroutinefunction(self._message_handler):
                                asyncio.run(self._message_handler(message_dict))
                            else:
                                self._message_handler(message_dict)
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to decode message JSON: {e}")
                            continue
                    self.channel.basic_ack(delivery_tag=method.delivery_tag)
            except Exception as e:
                logger.error(f"Error in consumer loop: {e}")
                break

    def set_paused(self, paused: bool):
        """Pause or resume message consumption."""
        with self._lock:
            self._paused = paused
        logger.info(f"Message consumption {'paused' if paused else 'resumed'}.")
        return True

    def publish(self, queue_name, message_data):
        """Publish a message to the specified RabbitMQ queue as JSON."""
        if not self.channel or not self.connection or not self.connection.is_open:
            logger.error(f"Cannot publish: not connected to RabbitMQ (queue: {queue_name})")
            return False
        try:
            self.channel.queue_declare(queue=queue_name, durable=True)
            self.channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=json.dumps(message_data),
                properties=pika.BasicProperties(delivery_mode=2)  # make message persistent
            )
            logger.info(f"Published message to {queue_name}: {message_data.get('message_id', 'N/A')}")
            return True
        except Exception as e:
            logger.error(f"Error publishing to queue {queue_name}: {e}")
            return False

    def cleanup(self):
        """Cleanly shut down consumer thread and close RabbitMQ resources."""
        # Signal the consumer thread to exit
        self._paused = True
        if hasattr(self, '_consumer_thread') and self._consumer_thread.is_alive():
            self._consumer_thread.join(timeout=5)
            logger.info("Consumer thread joined.")

        try:
            if self.channel and getattr(self.channel, 'is_open', False):
                self.channel.close()
                logger.info("RabbitMQ channel closed.")
        except Exception as e:
            logger.debug(f"Error closing RabbitMQ channel: {e}")

        try:
            if self.connection and getattr(self.connection, 'is_open', False):
                self.connection.close()
                logger.info("RabbitMQ connection closed.")
        except Exception as e:
            logger.debug(f"Error closing RabbitMQ connection: {e}")

        self._state_update('message_queue_status', 'disconnected')
        logger.info("RabbitMQ resources cleaned up.")