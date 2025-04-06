#!/usr/bin/env python3
import asyncio
import json
import websockets
import sys
import argparse

# Import these constants from your shared models if available 
# or define them here for standalone use
class MessageType:
    PING = "PING"
    PONG = "PONG"
    REGISTER_FRONTEND = "REGISTER_FRONTEND"
    REGISTER_FRONTEND_RESPONSE = "REGISTER_FRONTEND_RESPONSE"
    AGENT_STATUS_UPDATE = "AGENT_STATUS_UPDATE"

async def main(server_url):
    print(f"Connecting to server at {server_url} to check agent status...")
    async with websockets.connect(server_url) as websocket:
        print("Connected. Registering as frontend client...")
        
        # Register as a frontend
        register_message = {
            "message_type": MessageType.REGISTER_FRONTEND,
            "frontend_name": "DebugClient"
        }
        await websocket.send(json.dumps(register_message))
        
        # Wait for registration response
        response = await websocket.recv()
        response_data = json.loads(response)
        if response_data.get("message_type") == "REGISTER_FRONTEND_RESPONSE":
            frontend_id = response_data["frontend_id"]
            print(f"Registered as frontend with ID: {frontend_id}")
        else:
            print(f"Unexpected response: {response_data}")
            return
        
        # Now we should receive agent status updates
        print("Waiting for agent status updates (will wait up to 30 seconds)...")
        
        # Set a timeout for receiving messages
        try:
            message = await asyncio.wait_for(websocket.recv(), timeout=30)
            message_data = json.loads(message)
            
            if message_data.get("message_type") == MessageType.AGENT_STATUS_UPDATE:
                agents = message_data.get("agents", [])
                print(f"\n--- Agent Status Update Received ---")
                print(f"Total agents: {len(agents)}")
                print(f"Is full update: {message_data.get('is_full_update', False)}")
                
                if agents:
                    print("\nAGENTS:")
                    for agent in agents:
                        print(f"- ID: {agent.get('agent_id')}")
                        print(f"  Name: {agent.get('agent_name')}")
                        print(f"  Online: {agent.get('is_online')}")
                        print(f"  Last seen: {agent.get('last_seen')}")
                        print()
                else:
                    print("No agents in the update.")
            else:
                print(f"Received non-status message: {message_data}")
                
            # Force a full update to see all agents
            print("\nRequesting fresh status (PING)...")
            ping_message = {"message_type": MessageType.PING}
            await websocket.send(json.dumps(ping_message))
            
            # Wait for another response after PING
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5)
                message_data = json.loads(message)
                print(f"Received response after PING: {message_data.get('message_type')}")
                
                # Wait for one more message that might be agent status
                message = await asyncio.wait_for(websocket.recv(), timeout=5)
                message_data = json.loads(message)
                
                if message_data.get("message_type") == MessageType.AGENT_STATUS_UPDATE:
                    agents = message_data.get("agents", [])
                    print(f"\n--- Agent Status After PING ---")
                    print(f"Total agents: {len(agents)}")
                    
                    if agents:
                        print("\nAGENTS:")
                        for agent in agents:
                            print(f"- ID: {agent.get('agent_id')}")
                            print(f"  Name: {agent.get('agent_name')}")
                            print(f"  Online: {agent.get('is_online')}")
                            print(f"  Last seen: {agent.get('last_seen')}")
                            print()
                    else:
                        print("No agents in the update.")
            except asyncio.TimeoutError:
                print("No additional messages received after PING.")
            
        except asyncio.TimeoutError:
            print("No agent status updates received within 30 seconds.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug tool to check agent status")
    parser.add_argument("--url", default="ws://localhost:8000/ws", 
                        help="WebSocket URL of the server (default: ws://localhost:8000/ws)")
    args = parser.parse_args()
    
    try:
        asyncio.run(main(args.url))
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1) 