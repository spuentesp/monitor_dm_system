"""Test LLM connectivity via LLMRegistry with GitHub Models (current default)."""

import asyncio
from pydantic import BaseModel

from monitor_data.db.postgres import PostgresClient
from monitor_agents.llm_registry import LLMRegistry


class SimpleResponse(BaseModel):
    """A simple response model for testing."""

    greeting: str
    language: str


async def test_default_provider():
    pg = PostgresClient()
    await pg.connect()
    registry = LLMRegistry(pg)

    print("=== Test 1: Get default provider client ===")
    try:
        client = await registry.for_node("test_node")
        print(f"  Model: {client.model}")
        print(f"  Provider: {client.provider}")
        print(f"  Base URL: {client.base_url}")
    except Exception as e:
        print(f"  ERROR: {e}")
        await pg.close()
        return

    print("\n=== Test 2: Structured call (instructor) ===")
    try:
        result = await client.create(
            SimpleResponse,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that responds in JSON.",
                },
                {"role": "user", "content": "Greet me in Spanish."},
            ],
        )
        print(f"  Greeting: {result.greeting}")
        print(f"  Language: {result.language}")
        print("  ✅ Structured call works!")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n=== Test 3: Plain text completion ===")
    try:
        text = await client.complete_text(
            messages=[
                {"role": "system", "content": "You are a game master."},
                {"role": "user", "content": "Describe a tavern in one sentence."},
            ],
            max_tokens=100,
        )
        print(f"  Response: {text[:200]}")
        print("  ✅ Text completion works!")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n=== Test 4: Game system prompt ===")
    try:
        text = await client.complete_text(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a GM for D&D 5e. The player is creating a character. "
                        "Respond in character as a friendly GM. Be brief."
                    ),
                },
                {
                    "role": "user",
                    "content": "I want to create a character. What should I start with?",
                },
            ],
            max_tokens=150,
        )
        print(f"  GM Response: {text[:300]}")
        print("  ✅ Game system prompt works!")
    except Exception as e:
        print(f"  ERROR: {e}")

    await pg.close()
    print("\n=== All tests complete ===")


if __name__ == "__main__":
    asyncio.run(test_default_provider())
