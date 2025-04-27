# Configure pika logging first
import logging

from decorators import log_exceptions
logging.getLogger("pika").setLevel(logging.WARNING)

import os
import pika
import threading
import json
import time
from datetime import datetime
import uuid
from shared_models import MessageType, setup_logging
import asyncio  # Ensure asyncio is imported
import agent_config  # Import agent configuration

logger = setup_logging(__name__)
logger.propagate = False  # Prevent messages reaching the root logger

class MessageQueueHandler:
    """
    Handles all RabbitMQ connection, queue, and message operations for the agent.
    Reads host/port from environment or config internally. Only needs a logger.
    Message processing is handled by a user-provided callback.
    """
    def __init__(self, state_update=None, message_handler=None, loop: asyncio.AbstractEventLoop | None = None):
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
        self._event_loop = loop
        if asyncio.iscoroutinefunction(self._message_handler) and not self._event_loop:
            logger.error("Asynchronous message_handler provided without an event loop!")

    @log_exceptions
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
            if self._state_update:
                self._state_update('message_queue_status', 'connected')
            return True
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            return False

    @log_exceptions
    def _consumer_loop(self):
        """Consumer thread loop for processing messages from RabbitMQ."""
        logger.info(f"Starting consumer loop for queue: {self.queue_name}")
        while True:
            with self._lock:
                if self._paused:
                    time.sleep(agent_config.AGENT_PAUSED_CONSUMER_SLEEP)
                    continue
            method = None
            try:
                method, properties, body = self.channel.consume(self.queue_name, inactivity_timeout=1).__next__()
                if method is None:
                    continue
                logger.debug(f"Received message: {body[:100]}...")
                if self._message_handler:
                    try:
                        message_dict = json.loads(body.decode('utf-8'))
                        logger.debug(f"Decoded message dict: {message_dict}")
                        logger.info("Running sync handler directly...")
                        response = self._message_handler(message_dict)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to decode message JSON: {e} - Message Body: {body!r}")

                if method:
                    self.channel.basic_ack(delivery_tag=method.delivery_tag)
                    logger.debug(f"Acknowledged message {method.delivery_tag}")
            except StopIteration:
                continue
            except pika.exceptions.StreamLostError as e:
                logger.error(f"Connection lost in consumer loop: {e}. Attempting to reconnect...")
                break
        logger.warning(f"Consumer loop for queue {self.queue_name} has exited.")

    def _handle_async_callback_result(self, future: asyncio.Future):
        """Callback function to handle the result (or exception) of the async message handler."""
        result = future.result()
        logger.debug(f"Async message handler completed successfully. Result (if any): {result}")

    def set_consuming(self, consuming: bool):
        """Pause or resume message consumption."""
        with self._lock:
            self._consuming = consuming
        logger.info("Paused message consumption." if not self._consuming else "Resumed message consumption.")
        return True

    def cleanup(self):
        """Cleanly shut down consumer thread and close RabbitMQ resources."""
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
        if self._state_update:
            self._state_update('message_queue_status', 'disconnected')
        logger.info("RabbitMQ resources cleaned up.")