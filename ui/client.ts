const websocket = new WebSocket("ws://localhost:8765");
const messageInput = document.getElementById("messageInput") as HTMLInputElement;
const outputDiv = document.getElementById("output") as HTMLDivElement;

websocket.onopen = () => {
    console.log("Connected to WebSocket server");
};

websocket.onmessage = (event) => {
    const message = document.createElement("p");
    message.textContent = `Server: ${event.data}`;
    outputDiv.appendChild(message);
};

websocket.onclose = () => {
    console.log("Disconnected from WebSocket server");
};

websocket.onerror = (error) => {
    console.error("WebSocket error:", error);
};

function sendMessage() {
    if (websocket.readyState === WebSocket.OPEN) {
        const message = messageInput.value;
        websocket.send(message);
        const messageElement = document.createElement("p");
        messageElement.textContent = `Client: ${message}`;
        outputDiv.appendChild(messageElement);
        messageInput.value = "";
    } else {
        console.log("WebSocket connection is not open.");
    }
}