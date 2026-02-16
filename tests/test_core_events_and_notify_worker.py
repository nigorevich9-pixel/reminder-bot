import json
import unittest
import uuid
from contextlib import asynccontextmanager

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config.settings import settings
from app.repositories.core_tasks_repository import CoreTasksRepository
from app.worker.core_task_notify_worker import (
    process_core_codegen_notifications,
    process_core_needs_review_notifications,
    process_core_task_notifications,
    process_core_waiting_user_notifications,
)


class _StubBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((int(chat_id), str(text)))


@asynccontextmanager
async def _session():
    # Do NOT use app.db.AsyncSessionLocal in tests: it holds a global engine/pool
    # that is not compatible with unittest's per-test event loop.
    engine = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with SessionLocal() as session:
            yield session
    finally:
        await engine.dispose()


class TestCoreEventsAndNotifyWorker(unittest.IsolatedAsyncioTestCase):
    async def test_insert_event_writes_denormalized_columns(self) -> None:
        payload = {
            "event_type": "user_request",
            "tg": {"tg_id": 111, "chat_id": 222, "message_id": 333},
            "request": {"kind": "question", "text": "hello", "project_id": None, "attachments": []},
        }

        async with _session() as session:
            repo = CoreTasksRepository(session)
            external_id = f"t:{uuid.uuid4()}"
            event_id = await repo.insert_event(source="telegram", external_id=external_id, payload=payload)
            await session.commit()

            res = await session.execute(
                sa.text(
                    "SELECT event_type, tg_id, chat_id, request_kind, payload->>'event_type' AS et "
                    "FROM events WHERE id = :id"
                ),
                {"id": event_id},
            )
            row = res.mappings().one()
            self.assertEqual(row["event_type"], "user_request")
            self.assertEqual(int(row["tg_id"]), 111)
            self.assertEqual(int(row["chat_id"]), 222)
            self.assertEqual(row["request_kind"], "question")
            self.assertEqual(row["et"], "user_request")

    async def test_get_latest_codegen_job_returns_row(self) -> None:
        async with _session() as session:
            # Create user + task
            res = await session.execute(
                sa.text(
                    "INSERT INTO users (tg_id, username, first_name) "
                    "VALUES (:tg_id, NULL, NULL) "
                    "ON CONFLICT (tg_id) DO UPDATE SET tg_id = EXCLUDED.tg_id "
                    "RETURNING id"
                ),
                {"tg_id": 9010},
            )
            user_id = int(res.scalar_one())
            res = await session.execute(
                sa.text(
                    "INSERT INTO tasks (created_by_user_id, project_id, source, external_key, title, status) "
                    "VALUES (:uid, NULL, 'telegram', NULL, 't', 'NEEDS_REVIEW') "
                    "RETURNING id"
                ),
                {"uid": user_id},
            )
            task_id = int(res.scalar_one())
            await session.execute(
                sa.text(
                    "INSERT INTO codegen_jobs (task_id, repo_id, status, base_branch, branch_name, pr_url, error) "
                    "VALUES (:tid, NULL, 'DONE', 'main', 'ai/x', 'https://example/pr/1', NULL)"
                ),
                {"tid": task_id},
            )
            await session.commit()

        async with _session() as session:
            repo = CoreTasksRepository(session)
            job = await repo.get_latest_codegen_job(task_id=task_id)
            self.assertIsNotNone(job)
            assert job is not None
            self.assertEqual(job.get("status"), "DONE")
            self.assertEqual(job.get("pr_url"), "https://example/pr/1")

    async def test_send_to_user_transitions_to_done_and_sends_message(self) -> None:
        bot = _StubBot()

        async with _session() as session:
            # Create user
            res = await session.execute(
                sa.text(
                    "INSERT INTO users (tg_id, username, first_name) "
                    "VALUES (:tg_id, NULL, NULL) "
                    "ON CONFLICT (tg_id) DO UPDATE SET tg_id = EXCLUDED.tg_id "
                    "RETURNING id"
                ),
                {"tg_id": 9001},
            )
            user_id = int(res.scalar_one())

            # Create task in SEND_TO_USER
            res = await session.execute(
                sa.text(
                    "INSERT INTO tasks (created_by_user_id, project_id, source, external_key, title, status) "
                    "VALUES (:uid, NULL, 'telegram', NULL, 'q1', 'SEND_TO_USER') "
                    "RETURNING id"
                ),
                {"uid": user_id},
            )
            task_id = int(res.scalar_one())

            # Ensure our task is picked first (ordered by updated_at ASC).
            await session.execute(
                sa.text("UPDATE tasks SET updated_at = now() - interval '365 days' WHERE id = :id"),
                {"id": task_id},
            )

            # raw_input detail must include tg.chat_id and text
            await session.execute(
                sa.text("INSERT INTO task_details (task_id, kind, content) VALUES (:tid, 'raw_input', CAST(:c AS jsonb))"),
                {
                    "tid": task_id,
                    "c": json.dumps(
                        {"kind": "question", "text": "What?", "tg": {"chat_id": 12345, "tg_id": 9001}, "event_id": 1},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            )
            # llm_result must include answer
            await session.execute(
                sa.text("INSERT INTO task_details (task_id, kind, content) VALUES (:tid, 'llm_result', CAST(:c AS jsonb))"),
                {
                    "tid": task_id,
                    "c": json.dumps(
                        {
                            "llm_request_id": 1,
                            "answer": "Because.",
                            "clarify_question": None,
                            "json_invalid": False,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            )
            await session.commit()

        async with _session() as session:
            sent = await process_core_task_notifications(session, bot, limit=1)
            await session.commit()
            self.assertEqual(sent, 1)

            # ensure transitioned
            res = await session.execute(sa.text("SELECT status FROM tasks WHERE id = :id"), {"id": task_id})
            self.assertEqual(res.scalar_one(), "DONE")

        self.assertGreaterEqual(len(bot.sent), 1)
        matched = [(cid, text) for (cid, text) in bot.sent if cid == 12345]
        self.assertEqual(len(matched), 1)
        _chat_id, text = matched[0]
        self.assertIn("Ответ:", text)

    async def test_send_to_user_ignores_question_review_llm_result(self) -> None:
        bot = _StubBot()

        async with _session() as session:
            res = await session.execute(
                sa.text(
                    "INSERT INTO users (tg_id, username, first_name) "
                    "VALUES (:tg_id, NULL, NULL) "
                    "ON CONFLICT (tg_id) DO UPDATE SET tg_id = EXCLUDED.tg_id "
                    "RETURNING id"
                ),
                {"tg_id": 9003},
            )
            user_id = int(res.scalar_one())
            res = await session.execute(
                sa.text(
                    "INSERT INTO tasks (created_by_user_id, project_id, source, external_key, title, status) "
                    "VALUES (:uid, NULL, 'telegram', NULL, 'q3', 'SEND_TO_USER') "
                    "RETURNING id"
                ),
                {"uid": user_id},
            )
            task_id = int(res.scalar_one())
            await session.execute(
                sa.text("UPDATE tasks SET updated_at = now() - interval '365 days' WHERE id = :id"),
                {"id": task_id},
            )
            await session.execute(
                sa.text("INSERT INTO task_details (task_id, kind, content) VALUES (:tid, 'raw_input', CAST(:c AS jsonb))"),
                {
                    "tid": task_id,
                    "c": json.dumps(
                        {"kind": "question", "text": "What?", "tg": {"chat_id": 12346, "tg_id": 9003}, "event_id": 1},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            )
            await session.execute(
                sa.text("INSERT INTO task_details (task_id, kind, content) VALUES (:tid, 'llm_result', CAST(:c AS jsonb))"),
                {
                    "tid": task_id,
                    "c": json.dumps(
                        {"llm_request_id": 1, "answer": "Because.", "clarify_question": None, "json_invalid": False},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            )
            await session.execute(
                sa.text("INSERT INTO task_details (task_id, kind, content) VALUES (:tid, 'llm_result', CAST(:c AS jsonb))"),
                {
                    "tid": task_id,
                    "c": json.dumps(
                        {
                            "llm_request_id": 2,
                            "purpose": "question_review",
                            "answer": "{\"type\":\"approve\",\"notes\":\"ok\"}",
                            "clarify_question": None,
                            "json_invalid": False,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            )
            await session.commit()

        async with _session() as session:
            sent = await process_core_task_notifications(session, bot, limit=1)
            await session.commit()
            self.assertEqual(sent, 1)

        self.assertEqual(len(bot.sent), 1)
        chat_id, text = bot.sent[0]
        self.assertEqual(chat_id, 12346)
        self.assertIn("Because.", text)
        self.assertNotIn("approve", text)

    async def test_waiting_user_is_notified_once(self) -> None:
        bot = _StubBot()

        async with _session() as session:
            res = await session.execute(
                sa.text(
                    "INSERT INTO users (tg_id, username, first_name) "
                    "VALUES (:tg_id, NULL, NULL) "
                    "ON CONFLICT (tg_id) DO UPDATE SET tg_id = EXCLUDED.tg_id "
                    "RETURNING id"
                ),
                {"tg_id": 9002},
            )
            user_id = int(res.scalar_one())
            res = await session.execute(
                sa.text(
                    "INSERT INTO tasks (created_by_user_id, project_id, source, external_key, title, status) "
                    "VALUES (:uid, NULL, 'telegram', NULL, 'q2', 'WAITING_USER') "
                    "RETURNING id"
                ),
                {"uid": user_id},
            )
            task_id = int(res.scalar_one())
            await session.execute(
                sa.text("INSERT INTO task_details (task_id, kind, content) VALUES (:tid, 'raw_input', CAST(:c AS jsonb))"),
                {
                    "tid": task_id,
                    "c": json.dumps(
                        {"kind": "question", "text": "Hi", "tg": {"chat_id": 54321, "tg_id": 9002}, "event_id": 1},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            )
            await session.execute(
                sa.text("INSERT INTO task_details (task_id, kind, content) VALUES (:tid, 'llm_result', CAST(:c AS jsonb))"),
                {
                    "tid": task_id,
                    "c": json.dumps(
                        {"llm_request_id": 2, "answer": None, "clarify_question": "Clarify?", "json_invalid": False},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            )
            await session.commit()

        async with _session() as session:
            n1 = await process_core_waiting_user_notifications(session, bot, limit=5)
            await session.commit()
            n2 = await process_core_waiting_user_notifications(session, bot, limit=5)
            await session.commit()

            self.assertEqual(n1, 1)
            self.assertEqual(n2, 0)

            res = await session.execute(
                sa.text(
                    "SELECT COUNT(1) FROM task_details "
                    "WHERE task_id = :tid AND kind = 'tg_waiting_user_notified'"
                ),
                {"tid": task_id},
            )
            self.assertEqual(int(res.scalar_one()), 1)

        self.assertEqual(len(bot.sent), 1)
        chat_id, text = bot.sent[0]
        self.assertEqual(chat_id, 54321)
        self.assertIn("Нужно уточнение", text)

    async def test_waiting_user_uses_waiting_user_reason_when_llm_result_missing(self) -> None:
        bot = _StubBot()

        async with _session() as session:
            res = await session.execute(
                sa.text(
                    "INSERT INTO users (tg_id, username, first_name) "
                    "VALUES (:tg_id, NULL, NULL) "
                    "ON CONFLICT (tg_id) DO UPDATE SET tg_id = EXCLUDED.tg_id "
                    "RETURNING id"
                ),
                {"tg_id": 9004},
            )
            user_id = int(res.scalar_one())
            res = await session.execute(
                sa.text(
                    "INSERT INTO tasks (created_by_user_id, project_id, source, external_key, title, status) "
                    "VALUES (:uid, NULL, 'telegram', NULL, 't_wait', 'WAITING_USER') "
                    "RETURNING id"
                ),
                {"uid": user_id},
            )
            task_id = int(res.scalar_one())
            await session.execute(
                sa.text("INSERT INTO task_details (task_id, kind, content) VALUES (:tid, 'raw_input', CAST(:c AS jsonb))"),
                {
                    "tid": task_id,
                    "c": json.dumps(
                        {"kind": "task", "text": "Do X", "tg": {"chat_id": 65432, "tg_id": 9004}, "event_id": 1},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            )
            await session.execute(
                sa.text(
                    "INSERT INTO task_details (task_id, kind, content) VALUES (:tid, 'waiting_user_reason', CAST(:c AS jsonb))"
                ),
                {
                    "tid": task_id,
                    "c": json.dumps(
                        {"type": "review_clarify", "question": "Clarify?", "llm_request_id": 1},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            )
            await session.commit()

        async with _session() as session:
            n1 = await process_core_waiting_user_notifications(session, bot, limit=5)
            await session.commit()
            self.assertEqual(n1, 1)

        self.assertEqual(len(bot.sent), 1)
        chat_id, text = bot.sent[0]
        self.assertEqual(chat_id, 65432)
        self.assertIn("Clarify?", text)

    async def test_codegen_result_is_notified_once(self) -> None:
        bot = _StubBot()

        async with _session() as session:
            res = await session.execute(
                sa.text(
                    "INSERT INTO users (tg_id, username, first_name) "
                    "VALUES (:tg_id, NULL, NULL) "
                    "ON CONFLICT (tg_id) DO UPDATE SET tg_id = EXCLUDED.tg_id "
                    "RETURNING id"
                ),
                {"tg_id": 9011},
            )
            user_id = int(res.scalar_one())
            res = await session.execute(
                sa.text(
                    "INSERT INTO tasks (created_by_user_id, project_id, source, external_key, title, status) "
                    "VALUES (:uid, NULL, 'telegram', NULL, 't_codegen', 'NEEDS_REVIEW') "
                    "RETURNING id"
                ),
                {"uid": user_id},
            )
            task_id = int(res.scalar_one())
            await session.execute(
                sa.text("INSERT INTO task_details (task_id, kind, content) VALUES (:tid, 'raw_input', CAST(:c AS jsonb))"),
                {
                    "tid": task_id,
                    "c": json.dumps(
                        {"kind": "task", "text": "Do X", "tg": {"chat_id": 77777, "tg_id": 9011}, "event_id": 1},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            )
            await session.execute(
                sa.text(
                    "INSERT INTO task_details (task_id, kind, content) VALUES (:tid, 'codegen_result', CAST(:c AS jsonb))"
                ),
                {
                    "tid": task_id,
                    "c": json.dumps(
                        {
                            "worker": "core_codegen_worker",
                            "repo_full_name": "nigorevich9-pixel/reminder-bot",
                            "base_branch": "main",
                            "branch_name": "ai/task-1-reminder-bot",
                            "pr_url": "https://example/pr/42",
                            "tests": {"ok": True, "exit_code": 0, "output_tail": "OK"},
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            )
            await session.commit()

        async with _session() as session:
            n1 = await process_core_codegen_notifications(session, bot, limit=5)
            await session.commit()
            n2 = await process_core_codegen_notifications(session, bot, limit=5)
            await session.commit()

            self.assertEqual(n1, 1)
            self.assertEqual(n2, 0)
            res = await session.execute(
                sa.text("SELECT COUNT(1) FROM task_details WHERE task_id = :tid AND kind = 'tg_codegen_notified'"),
                {"tid": task_id},
            )
            self.assertEqual(int(res.scalar_one()), 1)

        self.assertEqual(len(bot.sent), 1)
        chat_id, text = bot.sent[0]
        self.assertEqual(chat_id, 77777)
        self.assertIn("PR:", text)
        self.assertIn("Tests: OK", text)

    async def test_needs_review_is_notified_per_transition(self) -> None:
        bot = _StubBot()

        async with _session() as session:
            res = await session.execute(
                sa.text(
                    "INSERT INTO users (tg_id, username, first_name) "
                    "VALUES (:tg_id, NULL, NULL) "
                    "ON CONFLICT (tg_id) DO UPDATE SET tg_id = EXCLUDED.tg_id "
                    "RETURNING id"
                ),
                {"tg_id": 9020},
            )
            user_id = int(res.scalar_one())
            res = await session.execute(
                sa.text(
                    "INSERT INTO tasks (created_by_user_id, project_id, source, external_key, title, status) "
                    "VALUES (:uid, NULL, 'telegram', NULL, 'nr', 'NEEDS_REVIEW') "
                    "RETURNING id"
                ),
                {"uid": user_id},
            )
            task_id = int(res.scalar_one())

            await session.execute(
                sa.text(
                    "INSERT INTO task_details (task_id, kind, content) VALUES (:tid, 'raw_input', CAST(:c AS jsonb))"
                ),
                {
                    "tid": task_id,
                    "c": json.dumps(
                        {"kind": "question", "text": "Q", "tg": {"chat_id": 88888, "tg_id": 9020}, "event_id": 1},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            )

            res = await session.execute(
                sa.text(
                    "INSERT INTO llm_requests (task_id, request_no, status, prompt, payload, locked_at, locked_by) "
                    "VALUES (:tid, 1, 'DONE', 'p', NULL, NULL, NULL) RETURNING id"
                ),
                {"tid": task_id},
            )
            llm_request_id = int(res.scalar_one())
            await session.execute(
                sa.text(
                    "INSERT INTO llm_responses (llm_request_id, task_id, backend, model, answer, error, latency_ms, meta) "
                    "VALUES (:rid, :tid, 'ollama', 'm', :answer, :err, NULL, NULL)"
                ),
                {
                    "rid": llm_request_id,
                    "tid": task_id,
                    "answer": json.dumps(
                        {"type": "final", "answer": "A", "approved": False, "review_notes": ""},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "err": "e1",
                },
            )
            await session.execute(
                sa.text("INSERT INTO task_details (task_id, kind, content) VALUES (:tid, 'llm_result', CAST(:c AS jsonb))"),
                {
                    "tid": task_id,
                    "c": json.dumps(
                        {"llm_request_id": llm_request_id, "answer": None, "clarify_question": None, "json_invalid": False},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
            )

            res = await session.execute(
                sa.text(
                    "INSERT INTO task_transitions (task_id, from_status, to_status, actor_user_id, reason) "
                    "VALUES (:tid, 'RUNNING', 'NEEDS_REVIEW', NULL, 'x') RETURNING id"
                ),
                {"tid": task_id},
            )
            transition_id_1 = int(res.scalar_one())

            await session.commit()

        async with _session() as session:
            n1 = await process_core_needs_review_notifications(session, bot, limit=5)
            await session.commit()
            n2 = await process_core_needs_review_notifications(session, bot, limit=5)
            await session.commit()
            self.assertEqual(n1, 1)
            self.assertEqual(n2, 0)
            res = await session.execute(
                sa.text(
                    "SELECT COUNT(1) FROM task_details "
                    "WHERE task_id = :tid AND kind = 'tg_needs_review_notified' "
                    "AND CAST(content->>'transition_id' AS int) = :tr"
                ),
                {"tid": task_id, "tr": transition_id_1},
            )
            self.assertEqual(int(res.scalar_one()), 1)

        self.assertEqual(len(bot.sent), 1)
        chat_id, text = bot.sent[0]
        self.assertEqual(chat_id, 88888)
        self.assertIn("NEEDS_REVIEW", text)
        self.assertIn("answer:", text)
        self.assertIn("A", text)
        self.assertIn("llm_error:", text)
        self.assertIn("e1", text)

        async with _session() as session:
            res = await session.execute(
                sa.text(
                    "INSERT INTO task_transitions (task_id, from_status, to_status, actor_user_id, reason) "
                    "VALUES (:tid, 'RUNNING', 'NEEDS_REVIEW', NULL, 'x2') RETURNING id"
                ),
                {"tid": task_id},
            )
            transition_id_2 = int(res.scalar_one())
            await session.commit()

        async with _session() as session:
            n3 = await process_core_needs_review_notifications(session, bot, limit=5)
            await session.commit()
            self.assertEqual(n3, 1)
            res = await session.execute(
                sa.text(
                    "SELECT COUNT(1) FROM task_details "
                    "WHERE task_id = :tid AND kind = 'tg_needs_review_notified' "
                    "AND CAST(content->>'transition_id' AS int) = :tr"
                ),
                {"tid": task_id, "tr": transition_id_2},
            )
            self.assertEqual(int(res.scalar_one()), 1)

