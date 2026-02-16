from __future__ import annotations

import hashlib
import json
from datetime import datetime

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

    async def insert_event(self, *, source: str, external_id: str, payload: dict) -> int:
        event_type = _payload_get_str(payload, "event_type")
        tg_id = _payload_get_int(payload, "tg", "tg_id")
        chat_id = _payload_get_int(payload, "tg", "chat_id")
        request_kind = _payload_get_str(payload, "request", "kind")

        res = await self._session.execute(
            sa.text(
                "INSERT INTO events (source, external_id, payload_hash, payload, event_type, tg_id, chat_id, request_kind) "
                "VALUES (:source, :external_id, :payload_hash, CAST(:payload AS jsonb), :event_type, :tg_id, :chat_id, :request_kind) "
                "RETURNING id"
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
        return int(res.scalar_one())

    async def get_task_id_by_event_id(self, *, event_id: int) -> int | None:
        res = await self._session.execute(
            sa.text(
                "SELECT task_id "
                "FROM task_details "
                "WHERE kind = 'raw_input' AND CAST(content->>'event_id' AS int) = :event_id "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"event_id": event_id},
        )
        task_id = res.scalar_one_or_none()
        return int(task_id) if isinstance(task_id, int) else None

    async def list_tasks_for_tg(self, *, tg_id: int, limit: int = 20) -> list[dict]:
        limit = max(min(int(limit), 100), 1)
        res = await self._session.execute(
            sa.text(
                "SELECT t.id, t.title, t.status, t.created_at, t.updated_at "
                "FROM tasks t "
                "JOIN users u ON u.id = t.created_by_user_id "
                "WHERE u.tg_id = :tg_id "
                "ORDER BY t.id DESC "
                "LIMIT :limit"
            ),
            {"tg_id": tg_id, "limit": limit},
        )
        return [dict(r) for r in res.mappings().all()]

    async def list_needs_review_tasks_for_tg(self, *, tg_id: int, limit: int = 50) -> list[dict]:
        limit = max(min(int(limit), 200), 1)
        res = await self._session.execute(
            sa.text(
                "SELECT "
                "  t.id, t.title, t.status, t.created_at, t.updated_at, tr.needs_review_at "
                "FROM tasks t "
                "JOIN users u ON u.id = t.created_by_user_id "
                "LEFT JOIN LATERAL ("
                "  SELECT created_at AS needs_review_at "
                "  FROM task_transitions "
                "  WHERE task_id = t.id AND to_status = 'NEEDS_REVIEW' "
                "  ORDER BY id DESC "
                "  LIMIT 1"
                ") tr ON true "
                "WHERE u.tg_id = :tg_id AND t.status = 'NEEDS_REVIEW' "
                "ORDER BY tr.needs_review_at ASC NULLS LAST, t.updated_at ASC "
                "LIMIT :limit"
            ),
            {"tg_id": tg_id, "limit": limit},
        )
        rows = []
        for r in res.mappings().all():
            d = dict(r)
            nra = d.get("needs_review_at")
            if isinstance(nra, datetime):
                d["needs_review_at"] = nra
            else:
                d["needs_review_at"] = None
            rows.append(d)
        return rows

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

    async def get_raw_input(self, *, task_id: int) -> dict | None:
        res = await self._session.execute(
            sa.text(
                "SELECT content "
                "FROM task_details "
                "WHERE task_id = :task_id AND kind = 'raw_input' "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"task_id": task_id},
        )
        row = res.mappings().first()
        return dict(row["content"]) if row and isinstance(row.get("content"), dict) else None

    async def get_latest_llm_result(self, *, task_id: int) -> dict | None:
        res = await self._session.execute(
            sa.text(
                "SELECT content "
                "FROM task_details "
                "WHERE task_id = :task_id AND kind = 'llm_result' "
                "AND (content->>'purpose' IS NULL OR content->>'purpose' IN ('', 'json_retry', 'question_rework', 'question_review_limit')) "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"task_id": task_id},
        )
        row = res.mappings().first()
        return dict(row["content"]) if row and isinstance(row.get("content"), dict) else None

    async def get_latest_waiting_user_reason(self, *, task_id: int) -> dict | None:
        res = await self._session.execute(
            sa.text(
                "SELECT content "
                "FROM task_details "
                "WHERE task_id = :task_id AND kind = 'waiting_user_reason' "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"task_id": task_id},
        )
        row = res.mappings().first()
        return dict(row["content"]) if row and isinstance(row.get("content"), dict) else None

    async def get_latest_codegen_result(self, *, task_id: int) -> dict | None:
        res = await self._session.execute(
            sa.text(
                "SELECT content "
                "FROM task_details "
                "WHERE task_id = :task_id AND kind = 'codegen_result' "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"task_id": task_id},
        )
        row = res.mappings().first()
        return dict(row["content"]) if row and isinstance(row.get("content"), dict) else None

    async def get_latest_codegen_job(self, *, task_id: int) -> dict | None:
        res = await self._session.execute(
            sa.text(
                "SELECT id, status, base_branch, branch_name, pr_url, error, created_at, started_at, finished_at "
                "FROM codegen_jobs "
                "WHERE task_id = :task_id "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"task_id": task_id},
        )
        row = res.mappings().first()
        return dict(row) if row else None

    async def pop_one_task_for_send_to_user(self) -> dict | None:
        res = await self._session.execute(
            sa.text(
                "SELECT id, title, status, created_at, updated_at "
                "FROM tasks "
                "WHERE status = 'SEND_TO_USER' "
                "ORDER BY updated_at ASC "
                "LIMIT 1 "
                "FOR UPDATE SKIP LOCKED"
            )
        )
        row = res.mappings().first()
        return dict(row) if row else None

    async def pop_one_task_for_waiting_user_notify(self) -> dict | None:
        res = await self._session.execute(
            sa.text(
                "SELECT t.id, t.title, t.status, t.created_at, t.updated_at "
                "FROM tasks t "
                "WHERE t.status = 'WAITING_USER' "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM task_details d "
                "  WHERE d.task_id = t.id AND d.kind = 'tg_waiting_user_notified'"
                ") "
                "ORDER BY t.updated_at ASC "
                "LIMIT 1 "
                "FOR UPDATE SKIP LOCKED"
            )
        )
        row = res.mappings().first()
        return dict(row) if row else None

    async def pop_one_task_for_codegen_notify(self) -> dict | None:
        res = await self._session.execute(
            sa.text(
                "SELECT t.id, t.title, t.status, t.created_at, t.updated_at "
                "FROM tasks t "
                "WHERE EXISTS ("
                "  SELECT 1 FROM task_details d "
                "  WHERE d.task_id = t.id AND d.kind = 'codegen_result'"
                ") "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM task_details d "
                "  WHERE d.task_id = t.id AND d.kind = 'tg_codegen_notified'"
                ") "
                "ORDER BY t.updated_at ASC "
                "LIMIT 1 "
                "FOR UPDATE SKIP LOCKED"
            )
        )
        row = res.mappings().first()
        return dict(row) if row else None

    async def pop_one_task_for_needs_review_notify(self) -> dict | None:
        res = await self._session.execute(
            sa.text(
                "SELECT t.id, t.title, t.status, t.created_at, t.updated_at, tr.transition_id "
                "FROM tasks t "
                "JOIN LATERAL ("
                "  SELECT id AS transition_id "
                "  FROM task_transitions "
                "  WHERE task_id = t.id AND to_status = 'NEEDS_REVIEW' "
                "  ORDER BY id DESC "
                "  LIMIT 1"
                ") tr ON true "
                "WHERE t.status = 'NEEDS_REVIEW' "
                "AND EXISTS ("
                "  SELECT 1 FROM task_details d "
                "  WHERE d.task_id = t.id AND d.kind = 'raw_input' AND d.content->>'kind' = 'question'"
                ") "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM task_details d "
                "  WHERE d.task_id = t.id AND d.kind = 'tg_needs_review_notified' "
                "  AND CAST(d.content->>'transition_id' AS int) = tr.transition_id"
                ") "
                "ORDER BY tr.transition_id ASC "
                "LIMIT 1 "
                "FOR UPDATE SKIP LOCKED"
            )
        )
        row = res.mappings().first()
        return dict(row) if row else None

    async def get_latest_llm_response_by_request_id(self, *, llm_request_id: int) -> dict | None:
        res = await self._session.execute(
            sa.text(
                "SELECT id, llm_request_id, task_id, backend, model, answer, error, created_at "
                "FROM llm_responses "
                "WHERE llm_request_id = :rid "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"rid": int(llm_request_id)},
        )
        row = res.mappings().first()
        return dict(row) if row else None

    async def insert_task_detail(self, *, task_id: int, kind: str, content: dict) -> int:
        res = await self._session.execute(
            sa.text(
                "INSERT INTO task_details (task_id, kind, content) "
                "VALUES (:task_id, :kind, CAST(:content AS jsonb)) "
                "RETURNING id"
            ),
            {"task_id": task_id, "kind": kind, "content": json.dumps(content, ensure_ascii=False, sort_keys=True)},
        )
        return int(res.scalar_one())

    async def transition_task(
        self,
        *,
        task_id: int,
        from_status: str,
        to_status: str,
        reason: str | None = None,
    ) -> bool:
        res = await self._session.execute(
            sa.text(
                "WITH updated AS ("
                "  UPDATE tasks "
                "  SET status = :to_status, updated_at = now() "
                "  WHERE id = :task_id AND status = :from_status "
                "  RETURNING id"
                ") "
                "INSERT INTO task_transitions (task_id, from_status, to_status, actor_user_id, reason) "
                "SELECT id, :from_status, :to_status, NULL, :reason "
                "FROM updated "
                "RETURNING task_id"
            ),
            {
                "task_id": task_id,
                "from_status": from_status,
                "to_status": to_status,
                "reason": reason,
            },
        )
        return res.scalar_one_or_none() is not None

