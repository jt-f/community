# Configure pika logging first
import logging
import os
import threading
import json
import time
from datetime import datetime
import uuid
import asyncio

# Third-party imports
import pika

# Local application imports
from shared_models import MessageType, setup_logging
from decorators import log_exceptions

logging.getLogger("pika").setLevel(logging.WARNING)

logger = setup_logging(__name__)
logger.propagate = False  # Prevent messages reaching the root logger


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

    @log_exceptions
    def connect(self, queue_name):
        """Connect to RabbitMQ, declare queue, and start consumer thread."""
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
        while True:
            with self._lock:
                if self._paused:
                    # If paused, wait briefly and check again
                    time.sleep(0.1) # Avoid busy-waiting
                    continue
            try:
                # Consume with a timeout to allow checking the pause flag
                for method, properties, body in self.channel.consume(self.queue_name, inactivity_timeout=1):
                    with self._lock:
                        if self._paused:
                            # If paused during consumption, break inner loop
                            break
                    if method is None:
                        continue  # Timeout occurred, loop again

                    if self._message_handler:
                        try:
                            message_dict = json.loads(body.decode('utf-8')) # Decode bytes to string first
                            # Optional: Handle specific message structures if needed
                            # Example: Convert gRPC message to serializable format
                            # if hasattr(message_dict, 'ListFields'):
                            #     message_dict = {k: v for k, v in message_dict.ListFields()}

                            # Handle synchronous or asynchronous message handler
                            if asyncio.iscoroutinefunction(self._message_handler):
                                # Running async function synchronously in a thread
                                asyncio.run(self._message_handler(message_dict))
                            else:
                                self._message_handler(message_dict)
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to decode message JSON: {e} - Body: {body!r}")
                            # Decide how to handle bad messages (e.g., Nack, requeue, log)
                            continue # Skip ack for this message
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")
                            # Decide how to handle processing errors
                            continue # Skip ack for this message

                    # Acknowledge the message after successful processing
                    self.channel.basic_ack(delivery_tag=method.delivery_tag)

            except StopIteration:
                # Expected when consume times out
                continue
            except pika.exceptions.StreamLostError as e:
                logger.error(f"Connection lost in consumer loop: {e}. Exiting loop.")
                # Consider adding reconnection logic here or signaling the main thread
                break # Exit loop on stream loss
            except Exception as e:
                logger.error(f"Unexpected error in consumer loop: {e}. Exiting loop.")
                break # Exit loop on unexpected errors

        logger.warning(f"Consumer loop for queue {self.queue_name} has exited.")
        if self._state_update:
             self._state_update('message_queue_status', 'disconnected') # Update state if loop exits

    @log_exceptions
    def set_paused(self, paused: bool):
        """Pause or resume message consumption."""
        with self._lock:
            self._paused = paused
        logger.info(f"Message consumption {'paused' if paused else 'resumed'}.")
        return True

    @log_exceptions
    def publish(self, queue_name, message_data):
        """Publish a message to the specified RabbitMQ queue as JSON."""
        if not self.channel or not self.connection or not self.connection.is_open:
            logger.error(f"Cannot publish: not connected to RabbitMQ (queue: {queue_name})")
            return False

        try:
            # Ensure the queue exists before publishing
            self.channel.queue_declare(queue=queue_name, durable=True)
            self.channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=json.dumps(message_data),
                properties=pika.BasicProperties(delivery_mode=2)  # make message persistent
            )
            msg_id = message_data.get('message_id', 'N/A')
            logger.info(f"Published message to {queue_name}: {msg_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to publish message to {queue_name}: {e}")
            return False

    @log_exceptions
    def cleanup(self):
        """Cleanly shut down consumer thread and close RabbitMQ resources."""
        logger.info("Initiating RabbitMQ resource cleanup...")
        # Signal the consumer thread to exit and wait for it
        self._paused = True
        if hasattr(self, '_consumer_thread') and self._consumer_thread.is_alive():
            logger.info("Waiting for consumer thread to join...")
            self._consumer_thread.join(timeout=5)
            if self._consumer_thread.is_alive():
                logger.warning("Consumer thread did not join within timeout.")
            else:
                logger.info("Consumer thread joined successfully.")

        # Close channel and connection safely
        try:
            if self.channel and getattr(self.channel, 'is_open', False):
                self.channel.close()
                logger.info("RabbitMQ channel closed.")
        except Exception as e:
            logger.error(f"Error closing RabbitMQ channel: {e}")

        try:
            if self.connection and getattr(self.connection, 'is_open', False):
                self.connection.close()
                logger.info("RabbitMQ connection closed.")
        except Exception as e:
            logger.error(f"Error closing RabbitMQ connection: {e}")

        if self._state_update:
            self._state_update('message_queue_status', 'disconnected')
        logger.info("RabbitMQ resource cleanup finished.")