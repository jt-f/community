"""Handles RabbitMQ connection, queue management, and message consumption for the agent."""
import asyncio
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import pika
import pika.exceptions

import agent_config
from decorators import log_exceptions
from shared_models import MessageType, setup_logging
from state import AgentState

# Configure pika logging first to avoid verbose output
logging.getLogger("pika").setLevel(logging.WARNING)

# Configure application logging
setup_logging()
logger = logging.getLogger(__name__)
logger.propagate = False # Prevent messages reaching the root logger


class MessageQueueHandler:
    """
    Manages RabbitMQ interactions: connection, queue declaration, message consumption,
    and publishing (though publishing might be handled elsewhere).
    Handles state updates via AgentState and message processing via a callback.
    """

    def __init__(self,
                 message_handler: Callable[[bytes], Any], # Handler takes bytes
                 state_manager: AgentState,
                 loop: asyncio.AbstractEventLoop):
        """Initialize the MessageQueueHandler."""
        self.rabbitmq_host = agent_config.RABBITMQ_HOST
        self.rabbitmq_port = agent_config.RABBITMQ_PORT
        self.connection: Optional[pika.BlockingConnection] = None
        self.channel: Optional[pika.channel.Channel] = None
        self.consumer_tag: Optional[str] = None
        self.queue_name: Optional[str] = None
        self._paused = False
        self._lock = threading.Lock() # Protects access to _paused and potentially channel/connection state
        self._message_handler = message_handler
        self._state_manager = state_manager
        self._event_loop = loop
        self._consumer_thread: Optional[threading.Thread] = None
        self._stop_consuming = threading.Event() # Signal to stop the consumer loop

        if asyncio.iscoroutinefunction(self._message_handler) and not self._event_loop:
            # This check is crucial if the handler is async
            logger.critical("Asynchronous message_handler provided without an event loop! Cannot schedule coroutines.")
            raise ValueError("Async message_handler requires an event loop.")

    @log_exceptions
    def connect(self, queue_name: str) -> bool:
        """Connect to RabbitMQ, declare the agent's queue, and start the consumer thread."""
        if self.connection and self.connection.is_open:
            logger.warning("Connection attempt while already connected.")
            return True

        self.queue_name = queue_name
        self._stop_consuming.clear() # Reset stop signal
        self._paused = False # Ensure not paused on new connection

        try:
            logger.info(f"Attempting to connect to RabbitMQ at {self.rabbitmq_host}:{self.rabbitmq_port}")
            self.connection = pika.BlockingConnection(pika.ConnectionParameters(
                host=self.rabbitmq_host,
                port=self.rabbitmq_port,
                connection_attempts=agent_config.RABBITMQ_CONNECTION_ATTEMPTS,
                retry_delay=agent_config.RABBITMQ_RETRY_DELAY,
                heartbeat=60 # Add heartbeat for robustness
            ))
            self.channel = self.connection.channel()
            # Declare the agent-specific queue
            self.channel.queue_declare(queue=self.queue_name, durable=True)

            # Start consumer in a separate thread
            self._consumer_thread = threading.Thread(target=self._consumer_loop, daemon=True)
            self._consumer_thread.start()
            logger.info("RabbitMQ consumer thread started.")
            # Schedule the async state update on the event loop
            asyncio.run_coroutine_threadsafe(self._state_manager.set_message_queue_status('connected'), self._event_loop)
            return True

        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}", exc_info=True)
            asyncio.run_coroutine_threadsafe(self._state_manager.set_message_queue_status('error'), self._event_loop)
            self.connection = None # Ensure connection is None on failure
            self.channel = None
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred during RabbitMQ connection: {e}", exc_info=True)
            asyncio.run_coroutine_threadsafe(self._state_manager.set_message_queue_status('error'), self._event_loop)
            self.connection = None
            self.channel = None
            return False

    def _consumer_loop(self):
        """The main loop for the consumer thread, handling messages."""
        logger.info("Consumer thread loop starting.")
        while not self._stop_consuming.is_set():
            try:
                with self._lock:
                    paused = self._paused # Check pause state under lock

                if paused:
                    # Sleep briefly when paused to avoid busy-waiting
                    time.sleep(agent_config.AGENT_PAUSED_CONSUMER_SLEEP)
                    continue

                if not self.channel or not self.channel.is_open:
                    logger.warning("Consumer loop: Channel is not open or available. Attempting to reconnect...")
                    # Schedule state update
                    asyncio.run_coroutine_threadsafe(self._state_manager.set_message_queue_status('disconnected'), self._event_loop)
                    time.sleep(agent_config.RABBITMQ_RETRY_DELAY)
                    continue # Skip this iteration

                # Use basic_get for the pause mechanism
                method_frame, header_frame, body = self.channel.basic_get(queue=self.queue_name, auto_ack=False)

                if method_frame:
                    logger.debug(f"Received message with delivery tag: {method_frame.delivery_tag}")
                    try:
                        # Schedule the message handler in the main event loop if it's async
                        if asyncio.iscoroutinefunction(self._message_handler):
                            future = asyncio.run_coroutine_threadsafe(self._message_handler(body), self._event_loop)
                            # Optional: Wait for the future if you need to handle exceptions from the handler here
                            # future.result() # This would block the consumer thread
                        else:
                            # Execute sync handler directly (careful about blocking)
                            self._message_handler(body)

                        # Acknowledge the message *after* successful scheduling/handling
                        if self.channel and self.channel.is_open:
                            self.channel.basic_ack(delivery_tag=method_frame.delivery_tag)
                            logger.debug(f"Acknowledged message {method_frame.delivery_tag}")
                        else:
                             logger.warning(f"Cannot ACK message {method_frame.delivery_tag}, channel closed.")
                    except Exception as e:
                        logger.error(f"Error processing message (delivery tag: {method_frame.delivery_tag}): {e}", exc_info=True)
                        # Negative acknowledgement - requeue=False to avoid poison messages
                        try:
                            if self.channel and self.channel.is_open:
                                self.channel.basic_nack(delivery_tag=method_frame.delivery_tag, requeue=False)
                                logger.warning(f"Negatively acknowledged message {method_frame.delivery_tag}")
                            else:
                                logger.warning(f"Cannot NACK message {method_frame.delivery_tag}, channel closed.")
                        except pika.exceptions.AMQPError as nack_err:
                            logger.error(f"Failed to NACK message {method_frame.delivery_tag}: {nack_err}")
                else:
                    # No message received, sleep briefly
                    time.sleep(agent_config.RABBITMQ_CONSUME_INACTIVITY_TIMEOUT)

            except pika.exceptions.ConnectionClosedByBroker:
                logger.warning("Consumer loop: Connection closed by broker. Stopping consumer.")
                asyncio.run_coroutine_threadsafe(self._state_manager.set_message_queue_status('disconnected'), self._event_loop)
                break # Exit loop
            except pika.exceptions.AMQPChannelError as ce:
                logger.error(f"Consumer loop: Channel error: {ce}. Stopping consumer.", exc_info=True)
                asyncio.run_coroutine_threadsafe(self._state_manager.set_message_queue_status('error'), self._event_loop)
                break # Exit loop
            except pika.exceptions.AMQPConnectionError as conn_err:
                logger.error(f"Consumer loop: Connection error: {conn_err}. Stopping consumer.", exc_info=True)
                asyncio.run_coroutine_threadsafe(self._state_manager.set_message_queue_status('error'), self._event_loop)
                break # Exit loop
            except Exception as e:
                logger.error(f"Consumer loop: Unexpected error: {e}. Stopping consumer.", exc_info=True)
                asyncio.run_coroutine_threadsafe(self._state_manager.set_message_queue_status('error'), self._event_loop)
                break # Exit loop

        logger.info("Consumer thread loop finished.")
        # Ensure channel/connection are cleaned up if loop exits unexpectedly
        self._safe_close_channel()
        self._safe_close_connection()

        # Final state update is now handled by the caller (Agent.cleanup_async)
        # asyncio.run_coroutine_threadsafe(self._state_manager.set_message_queue_status('disconnected'), self._event_loop)
        logger.info("Disconnected from RabbitMQ.")

    def pause_consumer(self):
        """Pause message consumption."""
        with self._lock:
            if not self._paused:
                logger.info("Pausing RabbitMQ consumer.")
                self._paused = True
                # Schedule state update
                asyncio.run_coroutine_threadsafe(self._state_manager.set_internal_state('paused'), self._event_loop)

    def resume_consumer(self):
        """Resume message consumption."""
        with self._lock:
            if self._paused:
                logger.info("Resuming RabbitMQ consumer.")
                self._paused = False
                # Agent state will be updated based on component status checks

    def _safe_close_channel(self):
        """Safely close the RabbitMQ channel if it's open."""
        if self.channel and self.channel.is_open:
            try:
                logger.info("Closing RabbitMQ channel.")
                self.channel.close()
            except Exception as e:
                logger.warning(f"Error closing RabbitMQ channel: {e}", exc_info=True)
        self.channel = None

    def _safe_close_connection(self):
        """Safely close the RabbitMQ connection if it's open."""
        if self.connection and self.connection.is_open:
            try:
                logger.info("Closing RabbitMQ connection.")
                self.connection.close()
            except Exception as e:
                logger.warning(f"Error closing RabbitMQ connection: {e}", exc_info=True)
        self.connection = None

    @log_exceptions
    def disconnect(self):
        """Disconnect from RabbitMQ and stop the consumer thread gracefully."""
        logger.info("Disconnecting from RabbitMQ...")
        # Schedule state update
        asyncio.run_coroutine_threadsafe(self._state_manager.set_message_queue_status('disconnecting'), self._event_loop)

        # Signal the consumer loop to stop
        self._stop_consuming.set()

        # Wait for the consumer thread to finish
        if self._consumer_thread and self._consumer_thread.is_alive():
            logger.info(f"Waiting up to {agent_config.MQ_CLEANUP_JOIN_TIMEOUT} seconds for consumer thread to join...")
            self._consumer_thread.join(timeout=agent_config.MQ_CLEANUP_JOIN_TIMEOUT)
            if self._consumer_thread.is_alive():
                logger.warning("Consumer thread did not join within timeout.")
            else:
                logger.info("Consumer thread joined successfully.")
        self._consumer_thread = None

        # Close channel and connection (might already be closed by consumer loop on error)
        self._safe_close_channel()
        self._safe_close_connection()

        # Final state update is now handled by the caller (Agent.cleanup_async)
        # asyncio.run_coroutine_threadsafe(self._state_manager.set_message_queue_status('disconnected'), self._event_loop)
        logger.info("Disconnected from RabbitMQ.")