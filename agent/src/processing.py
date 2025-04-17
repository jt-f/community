# Handles processing of incoming messages and queue consumption
import json
import time
import logging
from datetime import datetime
import uuid
from shared_models import MessageType
from publishing import publish_to_broker_input_queue

logger = logging.getLogger(__name__)

def generate_response(agent, message):
    sender_id = message.get("sender_id", "unknown")
    text_payload = message.get("text_payload", "")
    message_id = message.get("message_id", None)
    llm_response_text = "Sorry, I cannot generate a response right now."
    message_type = MessageType.REPLY
    if agent.mistral_client and text_payload:
        logger.info(f"Sending text to Mistral model {agent.mistral_model}...")
        try:
            chat_response = agent.mistral_client.chat.complete(
                model=agent.mistral_model,
                messages=[{"role": "user", "content": text_payload}]
            )
            logger.info(f'Mistral response: {chat_response.choices[0].message.content}')
            llm_response_text = chat_response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating with Mistral: {str(e)}")
            return {"error": str(e)}
    elif not agent.mistral_client:
        message_type = MessageType.ERROR
        logger.warning("Mistral client not available. Cannot generate LLM response.")
        llm_response_text = "LLM client is not configured."
    response = {
        "message_type": message_type,
        "sender_id": agent.agent_id,
        "receiver_id": sender_id,
        "text_payload": llm_response_text,
        "timestamp": datetime.now().isoformat(),
        "message_id": f"msg_{uuid.uuid4().hex}"
    }
    if message_id:
        response["in_reply_to_message_id"] = message_id
    return response


