"""
agent_init.py

Handles agent initialization logic including registration, RabbitMQ setup, and consumer.
"""

import os
import logging
import grpc_client

logger = logging.getLogger(__name__)

async def register_with_server(agent_id, agent_name):
    """
    Registers the agent with the server using gRPC.

    Args:
        agent_id (str): Unique identifier for the agent.
        agent_name (str): Name of the agent.

    Returns:
        bool: True if registration is successful, False otherwise.
    """
    try:
        # Get server host and port from environment or use defaults
        server_host = os.getenv("GRPC_HOST", "localhost")
        server_port = int(os.getenv("GRPC_PORT", "50051"))
        
        # Call gRPC client with correct parameter order
        response = await grpc_client.register_agent(
            server_host=server_host,
            server_port=server_port,
            name=agent_name,
            custom_id=agent_id
        )
        
        if response:
            logger.info(f"Agent {agent_name} registered successfully.")
            return True
        else:
            logger.error(f"Failed to register agent {agent_name}")
            return False
    except Exception as e:
        logger.error(f"Exception during registration: {e}")
        return False

def connect_rabbitmq(rabbitmq_host, rabbitmq_port, logger):
    """
    Connects to RabbitMQ server.

    Args:
        rabbitmq_host (str): Hostname of RabbitMQ server.
        rabbitmq_port (int): Port of RabbitMQ server.
        logger (logging.Logger): Logger instance.

    Returns:
        tuple: (pika.BlockingConnection, pika.channel.Channel) or (None, None) on failure.
    """
    try:
        import pika
        logger.info(f"Connecting to RabbitMQ at {rabbitmq_host}:{rabbitmq_port}")
        connection_params = pika.ConnectionParameters(host=rabbitmq_host, port=rabbitmq_port)
        connection = pika.BlockingConnection(connection_params)
        channel = connection.channel()
        logger.info(f"Connected to RabbitMQ server at {rabbitmq_host}:{rabbitmq_port}")
        return connection, channel
    except Exception as e:
        logger.error(f"Failed to connect to RabbitMQ at {rabbitmq_host}:{rabbitmq_port}: {e}")
        return None, None

def setup_rabbitmq_queue(channel, queue_name, callback, logger):
    """
    Sets up a RabbitMQ queue and binds a callback function.

    Args:
        channel (pika.Channel): RabbitMQ channel object.
        queue_name (str): Name of the queue.
        callback (function): Callback function to process messages.
        logger (logging.Logger): Logger instance.

    Returns:
        bool: True if setup was successful, False otherwise.
    """
    try:
        if not channel:
            logger.error("Cannot setup queue: RabbitMQ channel not established")
            return False
            
        # Declare the queue as durable to survive server restarts
        channel.queue_declare(queue=queue_name, durable=True)
        
        # Set up a consumer with callback
        channel.basic_consume(
            queue=queue_name,
            on_message_callback=callback,
            auto_ack=False  # We'll acknowledge manually after processing
        )
        
        logger.info(f"RabbitMQ queue {queue_name} set up successfully for message processing")
        return True
    except Exception as e:
        logger.error(f"Failed to setup queue {queue_name}: {e}")
        return False

def start_rabbitmq_consumer(agent):
    """
    Starts the RabbitMQ consumer for the agent, with reconnection and error handling.

    Args:
        agent (object): Agent instance containing RabbitMQ connection and channel.
    """
    if not agent.rabbitmq_connection or not agent.rabbitmq_connection.is_open:
        logger.error("Cannot start consumer: RabbitMQ connection not established")
        return
    try:
        logger.info(f"Starting to consume messages from queue {agent.queue_name}")
        while agent.running:
            try:
                agent.rabbitmq_connection.process_data_events(time_limit=1)
            except Exception as e:
                logger.error(f"Error in RabbitMQ consumer: {e}")
                import time
                time.sleep(1)
    except Exception as e:
        logger.error(f"Error in RabbitMQ consumer: {e}")
    finally:
        agent.cleanup()