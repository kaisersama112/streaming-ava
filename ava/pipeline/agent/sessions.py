"""Session helpers for OpenAI Agents SDK execution."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import threading
from typing import Any

try:
    from agents import SessionABC, SessionSettings, TResponseInputItem
except Exception:
    SessionABC = object  # type: ignore[assignment]
    SessionSettings = Any  # type: ignore[assignment]
    TResponseInputItem = Any  # type: ignore[assignment]

from ava.context_engine.types import ContextSnapshot
from configs import BASE_DIR, settings

_SESSION_CONTAINER_KEY = "sessions"
_SESSION_LOCK = threading.RLock()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return _json_safe(value.model_dump(mode="json"))
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe(value.to_dict())
    return str(value)


def _resolve_session_db_path() -> Path:
    configured = Path(
        str(getattr(settings.runtime, "agents_sdk_session_db", "state/agents_sessions.json") or "state/agents_sessions.json")
    )
    if configured.is_absolute():
        return configured
    return BASE_DIR / configured


class JsonFileSession(SessionABC):
    """Small JSON-backed SessionABC implementation.

    We keep this store separate from ConversationState so agent history can
    evolve independently without mutating the domain state schema.
    """

    def __init__(
        self,
        session_id: str,
        db_path: str | Path,
        session_settings: SessionSettings | None = None,
    ) -> None:
        self.session_id = session_id
        self.db_path = Path(db_path)
        self.session_settings = session_settings
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_container(self) -> dict[str, Any]:
        if not self.db_path.exists():
            return {_SESSION_CONTAINER_KEY: {}}
        try:
            payload = json.loads(self.db_path.read_text(encoding="utf-8"))
        except Exception:
            return {_SESSION_CONTAINER_KEY: {}}
        if not isinstance(payload, dict):
            return {_SESSION_CONTAINER_KEY: {}}
        sessions = payload.get(_SESSION_CONTAINER_KEY)
        if isinstance(sessions, dict):
            return payload
        return {_SESSION_CONTAINER_KEY: {}}

    def _save_container(self, container: dict[str, Any]) -> None:
        self.db_path.write_text(json.dumps(container, ensure_ascii=False, indent=2), encoding="utf-8")

    def _session_items(self, container: dict[str, Any]) -> list[dict[str, Any]]:
        sessions = container.setdefault(_SESSION_CONTAINER_KEY, {})
        payload = sessions.setdefault(self.session_id, {"items": []})
        items = payload.setdefault("items", [])
        if isinstance(items, list):
            return items
        payload["items"] = []
        return payload["items"]

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        with _SESSION_LOCK:
            items = list(self._session_items(self._load_container()))
        effective_limit = limit if limit is not None else getattr(self.session_settings, "limit", None)
        if effective_limit is None or effective_limit <= 0:
            return items
        return items[-effective_limit:]

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        if not items:
            return
        with _SESSION_LOCK:
            container = self._load_container()
            target = self._session_items(container)
            target.extend(_json_safe(item) for item in items)
            self._save_container(container)

    async def pop_item(self) -> TResponseInputItem | None:
        with _SESSION_LOCK:
            container = self._load_container()
            target = self._session_items(container)
            if not target:
                return None
            item = target.pop()
            self._save_container(container)
            return item

    async def clear_session(self) -> None:
        with _SESSION_LOCK:
            container = self._load_container()
            sessions = container.setdefault(_SESSION_CONTAINER_KEY, {})
            sessions[self.session_id] = {"items": []}
            self._save_container(container)


def build_agent_session(session_id: str) -> JsonFileSession:
    db_path = _resolve_session_db_path()
    return JsonFileSession(
        session_id=f"{session_id}:openai_agents_sdk",
        db_path=db_path,
    )


async def seed_agent_session_from_snapshot(session: JsonFileSession, snapshot: ContextSnapshot) -> None:
    seed_items: list[dict[str, object]] = []
    for item in snapshot.history_messages:
        role = str(item.get("role", "") or "").strip()
        content = item.get("content", "")
        if role not in {"user", "assistant", "system"}:
            continue
        if isinstance(content, str):
            text = content.strip()
            if not text:
                continue
            seed_items.append({"role": role, "content": text})
            continue
        if isinstance(content, list) and content:
            seed_items.append({"role": role, "content": content})

    existing = [_json_safe(item) for item in await session.get_items()]
    if existing == seed_items:
        return

    await session.clear_session()
    if seed_items:
        await session.add_items(seed_items)


async def clear_agent_session_async(session_id: str) -> None:
    session = build_agent_session(session_id)
    await session.clear_session()


def clear_agent_session(session_id: str) -> None:
    asyncio.run(clear_agent_session_async(session_id))
