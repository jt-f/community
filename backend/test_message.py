import requests
import time

def send_message(text):
    message = {'from': 'user', 'text': text}
    try:
        response = requests.post('http://172.19.36.55:5000/message', json=message)
        print(f"Sent message: {text} to 172.19.36.55:5000 with response: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending message: {e}")
        return False

if __name__ == "__main__":
    # Send a few test messages
    messages = [
        "Hello, this is a test message",
        "Testing the flow visualization",
        "Message number three"
    ]
    
    for message in messages:
        send_message(message)
        time.sleep(2)  # Wait 2 seconds between messages 