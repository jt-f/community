from fastapi import FastAPI, WebSocket
import asyncio

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Received message from client: {data}")
            await websocket.send_text(f"Echo: {data}")
    except Exception as e:
        print(f"WebSocket disconnected or error occurred: {e}")
    finally:
        pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8765)
