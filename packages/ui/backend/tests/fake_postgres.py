"""In-memory stand-in for PostgresClient's user/session/api-token/registry methods."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4


def _uid(value) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class FakePostgres:
    """In-memory stand-in for PostgresClient's user/session/api-token methods."""

    async def connect(self) -> None:
        """No-op: the fake is always 'connected'."""
        return None

    def __init__(self) -> None:
        self.users: dict[UUID, dict] = {}
        self.sessions: dict[str, dict] = {}
        self.tokens: dict[UUID, dict] = {}
        self._token_id_by_hash: dict[str, UUID] = {}
        self.oauth_accounts: dict[tuple[str, str], dict] = {}
        self.__init_registry__()

    async def user_create(self, user: dict) -> dict:
        uid = user.get("id") or uuid4()
        now = datetime.now(UTC)
        row = {
            "id": uid,
            "email": user["email"],
            "email_normalized": user["email_normalized"],
            "username": user["username"],
            "username_normalized": user["username_normalized"],
            "password_hash": user["password_hash"],
            "display_name": user.get("display_name", ""),
            "is_admin": bool(user.get("is_admin", False)),
            "email_verified": bool(user.get("email_verified", False)),
            "is_banned": bool(user.get("is_banned", False)),
            "banned_at": None,
            "banned_reason": None,
            "created_at": now,
            "updated_at": now,
        }
        self.users[uid] = row
        return row

    async def user_get_by_id(self, user_id: UUID) -> dict | None:
        return self.users.get(_uid(user_id))

    async def user_get_by_login(self, normalized_login: str) -> dict | None:
        for row in self.users.values():
            if row["email_normalized"] == normalized_login or row["username_normalized"] == normalized_login:
                return row
        return None

    async def user_update_password_hash(self, user_id: UUID, password_hash: str) -> None:
        uid = _uid(user_id)
        self.users[uid]["password_hash"] = password_hash
        self.users[uid]["updated_at"] = datetime.now(UTC)

    async def session_create(self, *, token_hash: str, user_id: UUID, expires_at) -> dict:
        now = datetime.now(UTC)
        row = {
            "token_hash": token_hash,
            "user_id": user_id,
            "created_at": now,
            "expires_at": expires_at,
            "last_seen_at": now,
        }
        self.sessions[token_hash] = row
        return row

    async def session_get(self, token_hash: str) -> dict | None:
        return self.sessions.get(token_hash)

    async def session_delete(self, token_hash: str) -> bool:
        return self.sessions.pop(token_hash, None) is not None

    async def sessions_list_for_user(self, user_id: UUID) -> list[dict]:
        rows = [r for r in self.sessions.values() if r["user_id"] == user_id]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return rows

    async def session_delete_all_for_user(self, user_id: UUID, except_token_hash: str | None = None) -> int:
        doomed = [h for h, r in self.sessions.items() if r["user_id"] == user_id and h != except_token_hash]
        for h in doomed:
            del self.sessions[h]
        return len(doomed)

    async def session_touch(self, token_hash: str) -> None:
        if token_hash in self.sessions:
            self.sessions[token_hash]["last_seen_at"] = datetime.now(UTC)

    async def api_token_create(self, token: dict) -> dict:
        tid = uuid4()
        row = {
            "id": tid,
            "user_id": token["user_id"],
            "name": token["name"],
            "token_prefix": token["token_prefix"],
            "token_hash": token["token_hash"],
            "created_at": datetime.now(UTC),
            "expires_at": token.get("expires_at"),
            "last_used_at": None,
            "revoked_at": None,
        }
        self.tokens[tid] = row
        self._token_id_by_hash[token["token_hash"]] = tid
        return row

    async def api_token_get_by_hash(self, token_hash: str) -> dict | None:
        tid = self._token_id_by_hash.get(token_hash)
        return self.tokens.get(tid) if tid is not None else None

    async def api_tokens_list(self, user_id: UUID) -> list[dict]:
        return [r for r in self.tokens.values() if r["user_id"] == user_id]

    async def api_token_revoke(self, token_id: UUID, user_id: UUID) -> bool:
        row = self.tokens.get(token_id)
        if row is not None and row["user_id"] == user_id and row["revoked_at"] is None:
            row["revoked_at"] = datetime.now(UTC)
            return True
        return False

    async def api_token_touch(self, token_hash: str) -> None:
        tid = self._token_id_by_hash.get(token_hash)
        if tid is not None:
            self.tokens[tid]["last_used_at"] = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Ownership registry (multiverses / worlds)
    # ------------------------------------------------------------------

    def __init_registry__(self) -> None:
        self.multiverses: dict[str, dict] = {}
        self.worlds: dict[str, dict] = {}

    async def multiverse_upsert(self, multiverse: dict) -> None:
        now = datetime.now(UTC)
        existing = self.multiverses.get(multiverse["id"])
        self.multiverses[multiverse["id"]] = {
            "id": multiverse["id"],
            "owner_id": multiverse.get("owner_id"),
            "label": multiverse["label"],
            "active": bool(multiverse.get("active", True)),
            "created_at": existing["created_at"] if existing else now,
            "updated_at": now,
        }

    async def multiverse_get_for_owner(self, multiverse_id: str, owner_id: UUID) -> dict | None:
        row = self.multiverses.get(multiverse_id)
        if row is not None and row["owner_id"] == owner_id:
            return row
        return None

    async def multiverses_list(self, owner_id: UUID) -> list[dict]:
        return [r for r in self.multiverses.values() if r["owner_id"] == owner_id]

    async def multiverse_delete(self, multiverse_id: str) -> None:
        self.multiverses.pop(multiverse_id, None)

    async def world_upsert(self, world: dict) -> None:
        now = datetime.now(UTC)
        existing = self.worlds.get(world["id"])
        self.worlds[world["id"]] = {
            "id": world["id"],
            "owner_id": world.get("owner_id"),
            "multiverse_id": world.get("multiverse_id"),
            "label": world["label"],
            "active": bool(world.get("active", True)),
            "created_at": existing["created_at"] if existing else now,
            "updated_at": now,
        }

    async def world_get_for_owner(self, world_id: str, owner_id: UUID) -> dict | None:
        row = self.worlds.get(world_id)
        if row is not None and row["owner_id"] == owner_id:
            return row
        return None

    async def worlds_list(self, owner_id: UUID, active_only: bool = False) -> list[dict]:
        rows = [r for r in self.worlds.values() if r["owner_id"] == owner_id]
        if active_only:
            rows = [r for r in rows if r["active"]]
        return rows

    async def world_get(self, world_id: str) -> dict | None:
        return self.worlds.get(world_id)

    async def world_delete(self, world_id: str) -> None:
        self.worlds.pop(world_id, None)

    # ------------------------------------------------------------------
    # OAuth accounts, banning, admin listing
    # ------------------------------------------------------------------

    async def user_set_email_verified(self, user_id: UUID, verified: bool) -> None:
        uid = _uid(user_id)
        self.users[uid]["email_verified"] = verified
        self.users[uid]["updated_at"] = datetime.now(UTC)

    async def user_set_banned(self, user_id: UUID, banned: bool, reason: str | None) -> bool:
        row = self.users.get(_uid(user_id))
        if row is None:
            return False
        row["is_banned"] = banned
        row["banned_reason"] = reason if banned else None
        row["banned_at"] = datetime.now(UTC) if banned else None
        row["updated_at"] = datetime.now(UTC)
        return True

    async def user_set_admin(self, user_id: UUID, is_admin: bool) -> bool:
        row = self.users.get(_uid(user_id))
        if row is None:
            return False
        row["is_admin"] = is_admin
        row["updated_at"] = datetime.now(UTC)
        return True

    async def users_list_admin(self, q: str | None, limit: int, offset: int) -> list[dict]:
        rows = sorted(self.users.values(), key=lambda r: r["created_at"], reverse=True)
        if q:
            needle = q.lower()
            rows = [r for r in rows if needle in r["email_normalized"] or needle in r["username_normalized"]]
        return rows[offset : offset + limit]

    async def users_count_admin(self, q: str | None) -> int:
        if not q:
            return len(self.users)
        needle = q.lower()
        return sum(
            1 for r in self.users.values() if needle in r["email_normalized"] or needle in r["username_normalized"]
        )

    async def oauth_account_upsert(self, account: dict) -> dict:
        key = (account["provider"], account["provider_account_id"])
        row = {
            "id": uuid4(),
            "user_id": account["user_id"],
            "provider": account["provider"],
            "provider_account_id": account["provider_account_id"],
            "email": account.get("email", ""),
            "created_at": datetime.now(UTC),
        }
        self.oauth_accounts[key] = row
        return row

    async def oauth_account_get(self, provider: str, provider_account_id: str) -> dict | None:
        return self.oauth_accounts.get((provider, provider_account_id))

    async def world_bindings_upsert(self, bindings: dict) -> None:
        """No-op stand-in for the legacy world_db_bindings table (unused for routing)."""
        return None

    async def world_bindings_get(self, world_id: str) -> dict | None:
        return None
