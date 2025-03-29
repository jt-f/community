from fastapi import FastAPI, WebSocket
import asyncio
import json
from src.models import ChatMessage, MessageType

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            try:
                # Parse incoming message
                message_data = json.loads(data)
                incoming_message = ChatMessage(**message_data)
                
                # Create echo response
                echo_message = ChatMessage.create(
                    sender_id="server",
                    receiver_id=incoming_message.sender_id,
                    text_payload=f"Echo: {incoming_message.text_payload}",
                    message_type=MessageType.TEXT
                )
                
                # Send echo response
                await websocket.send_text(echo_message.model_dump_json())
                
            except json.JSONDecodeError:
                # Handle invalid JSON
                error_message = ChatMessage.create(
                    sender_id="server",
                    receiver_id="unknown",
                    text_payload="Invalid message format",
                    message_type=MessageType.ERROR
                )
                await websocket.send_text(error_message.json())
                
    except Exception as e:
        print(f"WebSocket disconnected or error occurred: {e}")
    finally:
        pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8765)
