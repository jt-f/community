import asyncio
from app.core.agents.default import AnalystAgent
from app.core.models import Message

async def test__generate_response():
    agent = AnalystAgent()
    prompt = "Say a funny thing"
    model = "deepseek-r1:1.5b"
    parameters = None

    response = await agent._generate_response(prompt, model, parameters)
    print(response)

async def test_process_message():
    agent = AnalystAgent()
    message = Message(sender_id="test_user",message_type="test_message",content={"text": "Say a funny thing"})
    print(message.content)
    response = await agent.process_message(message=message)
    print(response)

if __name__ == "__main__":
    async def main():
        task1 = asyncio.create_task(test__generate_response())
        task2 = asyncio.create_task(test_process_message())

        await asyncio.gather(task1, task2)  # Run both tasks concurrently


    asyncio.run(main())