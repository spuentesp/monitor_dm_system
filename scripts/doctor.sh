#!/usr/bin/env bash
# doctor.sh — operator pre-launch check for the local stack.
#
# Sections:
#   1. `monitor ingest-doctor doctor`  (embedding + pairs + providers + jobs)
#   2. `monitor ingest-jobs list --stale`
#   3. Component reachability (neo4j / mongodb / qdrant / postgres / minio / llm)
#   4. Phase-0 preflight — HARD checks (these decide the exit code):
#        a. an active model pair exists and is compatible with llm_providers
#        b. every tier (light / standard / heavy / embedding) resolves to a
#           usable llm_providers row
#        c. every required store is reachable (additionally MinIO when
#           STORAGE_BACKEND=minio, GLiNER when NLP_BACKEND=gliner)
#        d. the embedding dimension agrees across .env (settings), the active
#           model pair and every live Qdrant collection
#
# Exit code 0 only when every section-4 check passes; non-zero otherwise.
# Sections 1-3 are informational and never override the section-4 verdict.

set -uo pipefail

cd "$(dirname "$0")/.."

# Pick up .env if present.
if [[ -f .env ]]; then
    # shellcheck disable=SC1091
    set -a; source .env; set +a
fi

PYTHON="${PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
    if [[ -x .venv/bin/python ]]; then
        PYTHON=".venv/bin/python"
    else
        PYTHON="python"
    fi
fi

echo "==> 1. monitor ingest-doctor doctor"
if ! "$PYTHON" -m monitor_cli.main ingest-doctor doctor --force; then
    echo "doctor command failed (non-fatal; see section 4 for the hard checks)"
fi

echo
echo "==> 2. monitor ingest-jobs list --stale"
"$PYTHON" -m monitor_cli.main ingest-jobs list --stale || true

echo
echo "==> 3. Component reachability"
"$PYTHON" - <<'PYEOF'
import asyncio
import json

from monitor_data.health import get_health_status

print(json.dumps(asyncio.run(get_health_status()), indent=2))
PYEOF

echo
echo "==> 4. Phase-0 preflight (hard checks)"
"$PYTHON" - <<'PYEOF'
import asyncio
import sys
import urllib.request

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"  {mark}  {name}{suffix}")
    if not ok:
        FAILURES.append(name)


def _usable(row: dict) -> bool:
    """Mirror LLMRegistry._is_provider_usable: a row is callable when it is
    connected, carries a key, or is a keyless local/custom endpoint."""
    status = (row.get("status") or "").lower()
    provider = (row.get("provider") or "").lower()
    if status == "error":
        return False
    if provider in {"ollama", "custom"}:
        return True
    if status == "connected":
        return True
    return bool(row.get("api_key"))


async def run() -> None:
    from monitor_data.config import settings
    from monitor_data.db.postgres import PostgresClient
    from monitor_data.db.qdrant import COLLECTION_CONFIGS, QdrantClient
    from monitor_data.retrieval.errors import IncompatiblePairError
    from monitor_data.retrieval.pairs import PairRegistry

    pg = PostgresClient()
    pair = None
    try:
        # 4a. active model pair + compatibility with llm_providers
        reg = PairRegistry(pg=pg)
        try:
            pair = await reg.validate_active_pair()
        except IncompatiblePairError as exc:
            check("active model pair", False, str(exc).splitlines()[0])
        else:
            check("active model pair", True, f"name={pair.name!r}")

        # 4b. every tier resolves to a usable provider
        for role in ("light", "standard", "heavy", "embedding"):
            rows = await pg.provider_list_by_role(role)
            usable = [r for r in rows if _usable(r)]
            if usable:
                first = usable[0]
                check(
                    f"tier {role}",
                    True,
                    f"{first.get('name')} ({first.get('model')}, {first.get('provider')})",
                )
            else:
                check(
                    f"tier {role}",
                    False,
                    f"no usable llm_providers row with role={role!r} "
                    f"({len(rows)} row(s) present)",
                )
    finally:
        await pg.close()

    # 4c. required stores reachable
    from monitor_data.health import get_health_status

    health = await get_health_status()
    components = health.get("components", {})
    required = ["neo4j", "mongodb", "qdrant", "postgres"]
    if (settings.storage_backend or "").lower() == "minio":
        required.append("minio")
    for name in required:
        comp = components.get(name) or {}
        status = comp.get("status", "unknown")
        check(f"store {name}", status == "healthy", f"status={status}")

    if (settings.nlp_backend or "").lower() == "gliner":
        gliner_url = (settings.gliner_url or "").rstrip("/")
        try:
            with urllib.request.urlopen(f"{gliner_url}/health", timeout=5) as resp:
                check("service gliner", resp.status == 200, f"status={resp.status}")
        except Exception as exc:  # noqa: BLE001 — any failure means unreachable
            check("service gliner", False, f"{gliner_url}/health unreachable: {exc}")

    # 4d. embedding dimension consistency (settings <-> pair <-> Qdrant)
    env_dim = int(settings.embedding_dimension)
    pair_dim = int(pair.embedding_dimension) if pair is not None else 0
    if pair is None:
        check("dimension settings<->pair", False, "no active pair to compare")
    else:
        check(
            "dimension settings<->pair",
            env_dim == pair_dim,
            f"settings.embedding_dimension={env_dim}, pair.embedding_dimension={pair_dim}",
        )

    qdrant = QdrantClient()
    client = qdrant.get_client()
    try:
        existing = await client.get_collections()
        names = {c.name for c in existing.collections}
        for collection in COLLECTION_CONFIGS:
            if collection not in names:
                continue
            info = await client.get_collection(collection_name=collection)
            vectors = info.config.params.vectors
            size = 0
            if hasattr(vectors, "size"):
                size = int(vectors.size or 0)
            elif isinstance(vectors, dict):
                for params in vectors.values():  # named vectors: use the first
                    size = int(getattr(params, "size", 0) or 0)
                    break
            want = pair_dim or env_dim
            check(
                f"dimension qdrant:{collection}",
                size == want,
                f"collection size={size}, expected {want}",
            )
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            result = close()
            if asyncio.iscoroutine(result):
                await result


asyncio.run(run())

if FAILURES:
    print(f"\n{len(FAILURES)} check(s) FAILED: {', '.join(FAILURES)}")
    sys.exit(1)
print("\nAll hard checks passed.")
PYEOF
exit $?
