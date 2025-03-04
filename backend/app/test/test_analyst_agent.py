import asyncio
import pytest
from app.core.agents.default import AnalystAgent
from app.core.models import Message

@pytest.mark.asyncio
async def test_generate_response():
    agent = AnalystAgent()
    prompt = "Say a funny thing"
    model = "deepseek-r1:1.5b"
    parameters = None

    response = await agent._generate_response(prompt, model, parameters)
    assert response is not None
    print(response)

@pytest.mark.asyncio
async def test_process_message():
    agent = AnalystAgent()
    message = Message(
        sender_id="test_user", 
        message_type="test_message", 
        content={"text": "Say a funny thing"}
    )
    
    response = await agent.process_message(message=message)
    assert response is not None
    assert response.sender_id == "analyst"
    assert "text" in response.content
    print(response.content["text"])

@pytest.mark.asyncio
async def test_think_once():
    agent = AnalystAgent()
    thought = await agent.think_once()
    assert thought is not None
    assert thought.message_type == "thought"
    assert "text" in thought.content
    print(thought.content["text"])

@pytest.mark.asyncio
async def test_agent_queue():
    agent = AnalystAgent()
    
    # Enqueue a message
    message = Message(
        sender_id="test_user", 
        message_type="test_message", 
        content={"text": "Hello agent"}
    )
    await agent.enqueue_message(message)
    
    # Get the message from the queue
    retrieved = await agent.get_next_message()
    assert retrieved is not None
    assert retrieved.sender_id == "test_user"
    assert retrieved.content["text"] == "Hello agent"
    
    # Queue should be empty now
    empty = await agent.get_next_message()
    assert empty is None

if __name__ == "__main__":
    async def main():
        await test_generate_response()
        await test_process_message()
        await test_think_once()
        await test_agent_queue()

    asyncio.run(main())