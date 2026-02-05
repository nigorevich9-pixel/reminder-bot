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
    async def asyncSetUp(self) -> None:
        async with _session() as session:
            res = await session.execute(sa.text("SELECT current_database()"))
            db_name = str(res.scalar_one())
            if not db_name.endswith("_test"):
                raise RuntimeError(f"Refusing to TRUNCATE non-test database: {db_name}")

            # Tests use a real Postgres database, so we must clean up between runs to avoid
            # flakiness from leftover rows (e.g. old SEND_TO_USER tasks).
            await session.execute(
                sa.text(
                    "TRUNCATE TABLE "
                    "task_transitions, task_details, tasks, users, events "
                    "RESTART IDENTITY CASCADE"
                )
            )
            await session.commit()

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
            sent = await process_core_task_notifications(session, bot, limit=5)
            await session.commit()
            self.assertEqual(sent, 1)

            # ensure transitioned
            res = await session.execute(sa.text("SELECT status FROM tasks WHERE id = :id"), {"id": task_id})
            self.assertEqual(res.scalar_one(), "DONE")

        self.assertEqual(len(bot.sent), 1)
        chat_id, text = bot.sent[0]
        self.assertEqual(chat_id, 12345)
        self.assertIn("Ответ:", text)

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

