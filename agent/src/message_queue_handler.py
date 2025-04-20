import os
import pika
import threading
import json
import time
import logging
from datetime import datetime
import uuid
from shared_models import MessageType
from messaging import publish_to_broker_input_queue

from shared_models import setup_logging
logger = setup_logging(__name__)
logger.propagate = False # Prevent messages reaching the root logger

# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
    logging.info("Loaded environment variables from .env file.")
except ImportError:
    logging.warning("python-dotenv not installed. .env file will not be loaded.")

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

    def connect(self, queue_name, message_handler=None):
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
            self._message_handler = message_handler or self._message_handler
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
                        self._message_handler(body)
                    self.channel.basic_ack(delivery_tag=method.delivery_tag)
            except Exception as e:
                logger.error(f"Error in consumer loop: {e}")
                break

    def set_consuming(self, consuming: bool):
        with self._lock:
            self._consuming = consuming
  
        logger.info("Paused message consumption." if not self._consuming else "Resumed message consumption.")
        return True

    def publish(self, queue_name, message_data):
        logger.warning("Not yet implemented.")
        pass

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