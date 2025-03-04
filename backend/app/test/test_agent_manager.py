import asyncio
import time
import pytest
from app.core.agent_manager import AgentManager
from app.core.agents.base import BaseAgent
from app.core.models import Message

class TestAgent(BaseAgent):
    def __init__(self, name="test_agent", think_interval=60.0):
        super().__init__(name=name, think_interval=think_interval)
        self.processed_messages = []
        self.thoughts_generated = 0
    
    async def process_message(self, message):
        self.processed_messages.append(message)
        return Message(
            sender_id=self.agent_id,
            message_type="response",
            content={"text": f"Processed: {message.content.get('text', '')}"}
        )
    
    async def think_once(self):
        self.thoughts_generated += 1
        self.last_think_time = time.time()
        return Message(
            sender_id=self.agent_id,
            message_type="thought",
            content={"text": f"Thought #{self.thoughts_generated}"}
        )
        
    async def think(self):
        """Implement the abstract think method required by BaseAgent."""
        thought = await self.think_once()
        yield thought

@pytest.mark.asyncio
async def test_agent_manager():
    # Clear registries before test
    BaseAgent.clear_registries()
    
    # Create manager and agents
    manager = AgentManager()
    agent1 = TestAgent("agent1")
    agent2 = TestAgent("agent2")
    
    # Register agents
    manager.register_agent(agent1)
    manager.register_agent(agent2)
    
    # Enqueue messages
    message1 = Message(sender_id="user", message_type="user_message", content={"text": "Hello agent1"})
    message2 = Message(sender_id="user", message_type="user_message", content={"text": "Hello agent2"})
    
    await agent1.enqueue_message(message1)
    await agent2.enqueue_message(message2)
    
    # Start manager in background
    task = asyncio.create_task(manager.run())
    
    # Give it some time to process
    await asyncio.sleep(2)
    
    # Stop manager
    manager.stop()
    await task
    
    # Check results
    assert len(agent1.processed_messages) == 1
    assert agent1.processed_messages[0].content["text"] == "Hello agent1"
    
    assert len(agent2.processed_messages) == 1
    assert agent2.processed_messages[0].content["text"] == "Hello agent2"
    
    # Both agents should have thought at least once
    assert agent1.thoughts_generated >= 1
    assert agent2.thoughts_generated >= 1

if __name__ == "__main__":
    asyncio.run(test_agent_manager())