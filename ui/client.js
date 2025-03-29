var websocket = new WebSocket("ws://localhost:8765");
var messageInput = document.getElementById("messageInput");
var outputDiv = document.getElementById("output");
websocket.onopen = function () {
    console.log("Connected to WebSocket server");
};
websocket.onmessage = function (event) {
    var message = document.createElement("p");
    message.textContent = "Server: ".concat(event.data);
    outputDiv.appendChild(message);
};
websocket.onclose = function () {
    console.log("Disconnected from WebSocket server");
};
websocket.onerror = function (error) {
    console.error("WebSocket error:", error);
};
function sendMessage() {
    if (websocket.readyState === WebSocket.OPEN) {
        var message = messageInput.value;
        websocket.send(message);
        var messageElement = document.createElement("p");
        messageElement.textContent = "Client: ".concat(message);
        outputDiv.appendChild(messageElement);
        messageInput.value = "";
    }
    else {
        console.log("WebSocket connection is not open.");
    }
}
