import asyncio
import logging
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.db import AsyncSessionLocal
from app.repositories.core_tasks_repository import CoreTasksRepository


if TYPE_CHECKING:
    from aiogram import Bot
else:
    Bot = object  # type: ignore[misc,assignment]


logger = logging.getLogger("core_task_notify_worker")
CONSUMER_NAME = "reminder_bot_core_task_notify_worker"


def _extract_chat_id(raw_input: dict) -> int | None:
    tg = raw_input.get("tg")
    if not isinstance(tg, dict):
        return None
    chat_id = tg.get("chat_id")
    return int(chat_id) if isinstance(chat_id, int) and chat_id else None


def _extract_question_text(raw_input: dict) -> str | None:
    text = raw_input.get("text")
    return text.strip() if isinstance(text, str) and text.strip() else None


def _extract_answer_text(llm_result: dict) -> str | None:
    answer = llm_result.get("answer")
    return answer.strip() if isinstance(answer, str) and answer.strip() else None


def _extract_clarify_question(llm_result: dict) -> str | None:
    q = llm_result.get("clarify_question")
    return q.strip() if isinstance(q, str) and q.strip() else None


def _format_message(*, task_id: int, question: str, answer: str) -> str:
    return f"task #{task_id}\n\nВопрос:\n{question}\n\nОтвет:\n{answer}"


def _format_clarify_message(*, task_id: int, question: str) -> str:
    return (
        f"task #{task_id}\n\n"
        f"Нужно уточнение:\n{question}\n\n"
        f"Ответь командой:\n/ask {task_id} <твой ответ>"
    )


async def _process_one(session: AsyncSession, bot: Bot) -> bool:
    repo = CoreTasksRepository(session)
    task = await repo.pop_one_task_for_send_to_user()
    if not task:
        return False

    task_id = int(task["id"])
    raw_input = await repo.get_raw_input(task_id=task_id)
    llm_result = await repo.get_latest_llm_result(task_id=task_id)

    if not raw_input or not llm_result:
        await repo.transition_task(
            task_id=task_id,
            from_status="SEND_TO_USER",
            to_status="FAILED",
            reason=f"{CONSUMER_NAME}: missing raw_input/llm_result",
        )
        await session.commit()
        return True

    chat_id = _extract_chat_id(raw_input)
    question = _extract_question_text(raw_input)
    answer = _extract_answer_text(llm_result)

    if chat_id is None or question is None or answer is None:
        await repo.transition_task(
            task_id=task_id,
            from_status="SEND_TO_USER",
            to_status="FAILED",
            reason=f"{CONSUMER_NAME}: missing chat_id/question/answer",
        )
        await session.commit()
        return True

    msg = _format_message(task_id=task_id, question=question, answer=answer)
    try:
        await bot.send_message(chat_id=chat_id, text=msg)
    except Exception as exc:
        logger.warning("Failed to send task %s: %s", task_id, exc)
        await session.rollback()
        return True

    ok = await repo.transition_task(
        task_id=task_id,
        from_status="SEND_TO_USER",
        to_status="DONE",
        reason=f"{CONSUMER_NAME}: sent",
    )
    if not ok:
        logger.warning("Failed to transition task %s SEND_TO_USER -> DONE", task_id)
        await session.rollback()
        return True

    await session.commit()
    return True


async def _process_one_waiting_user(session: AsyncSession, bot: Bot) -> bool:
    repo = CoreTasksRepository(session)
    task = await repo.pop_one_task_for_waiting_user_notify()
    if not task:
        return False

    task_id = int(task["id"])
    raw_input = await repo.get_raw_input(task_id=task_id)
    llm_result = await repo.get_latest_llm_result(task_id=task_id)

    if not raw_input or not llm_result:
        await repo.insert_task_detail(
            task_id=task_id,
            kind="tg_waiting_user_notified",
            content={"error": "missing raw_input/llm_result", "worker": CONSUMER_NAME},
        )
        await session.commit()
        return True

    chat_id = _extract_chat_id(raw_input)
    question = _extract_clarify_question(llm_result)

    if chat_id is None or question is None:
        await repo.insert_task_detail(
            task_id=task_id,
            kind="tg_waiting_user_notified",
            content={"error": "missing chat_id/clarify_question", "worker": CONSUMER_NAME},
        )
        await session.commit()
        return True

    msg = _format_clarify_message(task_id=task_id, question=question)
    try:
        await bot.send_message(chat_id=chat_id, text=msg)
    except Exception as exc:
        logger.warning("Failed to send clarify for task %s: %s", task_id, exc)
        await session.rollback()
        return True

    await repo.insert_task_detail(
        task_id=task_id,
        kind="tg_waiting_user_notified",
        content={"worker": CONSUMER_NAME},
    )
    await session.commit()
    return True


async def process_core_task_notifications(session: AsyncSession, bot: Bot, *, limit: int = 10) -> int:
    processed = 0
    for _ in range(max(int(limit), 1)):
        if not await _process_one(session, bot):
            break
        processed += 1
    return processed


async def process_core_waiting_user_notifications(session: AsyncSession, bot: Bot, *, limit: int = 10) -> int:
    processed = 0
    for _ in range(max(int(limit), 1)):
        if not await _process_one_waiting_user(session, bot):
            break
        processed += 1
    return processed


async def run_loop() -> None:
    if not settings.tg_token:
        raise RuntimeError("TG_TOKEN is not set")

    bot = Bot(token=settings.tg_token)
    poll_seconds = max(int(settings.worker_poll_seconds), 1)
    while True:
        async with AsyncSessionLocal() as session:
            try:
                processed = await process_core_task_notifications(session, bot, limit=10)
                if processed:
                    logger.info("Sent %s core task notifications", processed)

                clarify_processed = await process_core_waiting_user_notifications(session, bot, limit=10)
                if clarify_processed:
                    logger.info("Sent %s core waiting-user notifications", clarify_processed)
            except Exception as exc:
                logger.exception("Worker error: %s", exc)
        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_loop())

