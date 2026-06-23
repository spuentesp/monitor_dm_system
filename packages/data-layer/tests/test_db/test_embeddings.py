import pytest

from monitor_data.db import embeddings


async def _fail_embedding(*args, **kwargs):
    raise RuntimeError("missing api key")


@pytest.mark.asyncio
async def test_embed_text_falls_back_when_remote_embedding_unavailable(monkeypatch):
    monkeypatch.setattr(embeddings.litellm, "aembedding", _fail_embedding)

    vector = await embeddings.embed_text("Death in Space should still index offline")

    assert isinstance(vector, list)
    assert len(vector) == 1536
    assert any(value != 0.0 for value in vector)


@pytest.mark.asyncio
async def test_embed_batch_falls_back_when_remote_embedding_unavailable(monkeypatch):
    monkeypatch.setattr(embeddings.litellm, "aembedding", _fail_embedding)

    vectors = await embeddings.embed_batch(
        [
            "rules tables and prices",
            "setting lore and factions",
        ]
    )

    assert len(vectors) == 2
    assert all(len(vector) == 1536 for vector in vectors)
    assert vectors[0] != vectors[1]
