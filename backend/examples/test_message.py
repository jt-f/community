import requests
import time
from datetime import datetime
import argparse

def send_message(text, target_id=None):
    """Send a message to either all agents or a specific target"""
    message = {
        'sender_id': 'human',
        'sender_name': 'Human',
        'content': text,
        'recipient_id': target_id,  # None for broadcast, specific ID for direct message
        'timestamp': datetime.now().isoformat(),
        'metadata': {}
    }
    try:
        response = requests.post('http://172.19.36.55:8000/message', json=message)
        target_info = f" to {target_id}" if target_id else " to all agents"
        print(f"Sent message{target_info}: {text}")
        print(f"Response status: {response.status_code}")
        if response.status_code != 200:
            print(f"Error response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending message: {e}")
        return False

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Send test messages to agents')
    parser.add_argument('--target', '-t', help='Target agent ID (optional, broadcasts to all if not specified)')
    parser.add_argument('--message', '-m', help='Message to send')
    args = parser.parse_args()

    # Test messages
    messages = [
        "Hello agents, this is a test message from Human",
        "Can anyone help me analyze this data?",
        "Please respond to this message"
    ] if not args.message else [args.message]
    
    print("Starting test message sequence...")
    print(f"Target: {'all agents' if not args.target else args.target}")
    
    for message in messages:
        success = send_message(message, args.target)
        print(f"Message sent successfully: {success}\n")
        time.sleep(2)  # Wait 2 seconds between messages
    
    print("Test message sequence complete.")

if __name__ == "__main__":
    main() 