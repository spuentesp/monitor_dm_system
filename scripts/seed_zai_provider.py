import os
"""Seed z.ai (ZhipuAI) provider into PostgreSQL."""

import asyncio
from monitor_data.db.postgres import PostgresClient


async def seed_zai():
    pg = PostgresClient()
    await pg.connect()

    provider = {
        "id": "zai-z1-flash",
        "name": "Z.ai (GLM-Z1-Flash)",
        "provider": "custom",
        "model": "glm-z1-flash",
        "api_key": os.environ.get("ZAI_API_KEY", ""),  # redacted: set via env,
        "base_url": "https://api.z.ai/api/coding/paas/v4",
        "model_params": {"temperature": 0.7, "max_tokens": 4096},
        "role": "standard",
        "is_default": False,
    }

    await pg.provider_upsert(provider)
    print(f"Seeded provider: {provider['id']}")

    providers = await pg.providers_list()
    print(f"\nProviders ({len(providers)}):")
    for p in providers:
        default_marker = " [DEFAULT]" if p.get("is_default") else ""
        print(f"  - {p['id']}: {p['provider']} / {p['model']}{default_marker}")

    await pg.close()


if __name__ == "__main__":
    asyncio.run(seed_zai())
