import asyncio
from app.utils.ollama import OllamaClient

async def test_generate():
    client = OllamaClient()
    prompt = "Say a funny thing"
    model = "deepseek-r1:1.5b"
    parameters = None

    response = await client.generate(prompt, model, parameters)
    print(response)

if __name__ == "__main__":
    asyncio.run(test_generate())