from __future__ import annotations

import hashlib
import json

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


def _payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()

def _payload_get_int(payload: dict, *path: str) -> int | None:
    cur = payload
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    if cur is None:
        return None
    if isinstance(cur, int):
        return cur
    if isinstance(cur, str) and cur.isdigit():
        return int(cur)
    return None

def _payload_get_str(payload: dict, *path: str) -> str | None:
    cur = payload
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur if isinstance(cur, str) and cur else None


class CoreTasksRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def insert_event(self, *, source: str, external_id: str, payload: dict) -> None:
        event_type = _payload_get_str(payload, "event_type")
        tg_id = _payload_get_int(payload, "tg", "tg_id")
        chat_id = _payload_get_int(payload, "tg", "chat_id")
        request_kind = _payload_get_str(payload, "request", "kind")

        await self._session.execute(
            sa.text(
                "INSERT INTO events (source, external_id, payload_hash, payload, event_type, tg_id, chat_id, request_kind) "
                "VALUES (:source, :external_id, :payload_hash, CAST(:payload AS jsonb), :event_type, :tg_id, :chat_id, :request_kind)"
            ),
            {
                "source": source,
                "external_id": external_id,
                "payload_hash": _payload_hash(payload),
                "payload": json.dumps(payload, ensure_ascii=False, sort_keys=True),
                "event_type": event_type,
                "tg_id": tg_id,
                "chat_id": chat_id,
                "request_kind": request_kind,
            },
        )

    async def get_task(self, *, task_id: int) -> dict | None:
        res = await self._session.execute(
            sa.text("SELECT id, title, status, created_at, updated_at FROM tasks WHERE id = :id"),
            {"id": task_id},
        )
        row = res.mappings().first()
        return dict(row) if row else None

    async def get_latest_llm_answer(self, *, task_id: int) -> str | None:
        res = await self._session.execute(
            sa.text(
                "SELECT content->>'answer' AS answer "
                "FROM task_details "
                "WHERE task_id = :task_id AND kind = 'llm_result' "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"task_id": task_id},
        )
        return res.scalar_one_or_none()

