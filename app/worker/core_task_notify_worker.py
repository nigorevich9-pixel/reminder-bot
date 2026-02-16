import asyncio
import json
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


def _extract_waiting_reason_question(waiting_reason: dict | None) -> str | None:
    if not isinstance(waiting_reason, dict):
        return None
    q = waiting_reason.get("question")
    return q.strip() if isinstance(q, str) and q.strip() else None


def _format_message(*, task_id: int, question: str, answer: str) -> str:
    return f"task #{task_id}\n\nВопрос:\n{question}\n\nОтвет:\n{answer}"


def _format_clarify_message(*, task_id: int, question: str) -> str:
    return (
        f"task #{task_id}\n\n"
        f"Нужно уточнение:\n{question}\n\n"
        f"Ответь командой:\n/ask {task_id} <твой ответ>"
    )


def _format_codegen_message(
    *,
    task_id: int,
    title: str,
    pr_url: str | None,
    tests_ok: bool | None,
    repo_full_name: str | None,
    branch_name: str | None,
) -> str:
    lines = [f"task #{task_id}", f"{title}".strip(), ""]
    if pr_url:
        lines.append(f"PR: {pr_url}")
    if repo_full_name:
        lines.append(f"Repo: {repo_full_name}")
    if branch_name:
        lines.append(f"Branch: {branch_name}")
    if tests_ok is True:
        lines.append("Tests: OK")
    elif tests_ok is False:
        lines.append("Tests: FAILED")
    else:
        lines.append("Tests: (unknown)")
    return "\n".join([l for l in lines if l is not None]).strip()

def _strip_markdown_fences(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return raw
    if not raw.startswith("```"):
        return raw
    lines = raw.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    return raw

def _extract_json_answer(raw_answer: str | None) -> str | None:
    if raw_answer is None:
        return None
    raw = _strip_markdown_fences(raw_answer)
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except Exception:
        return raw
    if isinstance(obj, dict) and isinstance(obj.get("answer"), str) and obj.get("answer").strip():
        return obj.get("answer").strip()
    return raw

def _format_needs_review_message(
    *,
    task_id: int,
    answer: str | None,
    llm_error: str | None,
    pr_url: str | None,
    pr_error: str | None,
) -> str:
    lines = [f"task #{task_id}", "", "NEEDS_REVIEW"]
    if answer:
        lines.extend(["", "answer:", answer])
    if llm_error:
        lines.extend(["", "llm_error:", llm_error])
    if pr_url and pr_error:
        lines.extend(["", "pr_url:", pr_url, "", "pr_error:", pr_error])
    return "\n".join(lines).strip()


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
        logger.warning("Failed to send task %s to chat_id=%s: %s", task_id, chat_id, exc)
        ok = await repo.transition_task(
            task_id=task_id,
            from_status="SEND_TO_USER",
            to_status="FAILED",
            reason=f"{CONSUMER_NAME}: tg send failed: {exc}",
        )
        if not ok:
            logger.warning("Failed to transition task %s SEND_TO_USER -> FAILED", task_id)
            await session.rollback()
            return True
        await session.commit()
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


async def _process_one_needs_review(session: AsyncSession, bot: Bot) -> bool:
    repo = CoreTasksRepository(session)
    task = await repo.pop_one_task_for_needs_review_notify()
    if not task:
        return False

    task_id = int(task["id"])
    transition_id = task.get("transition_id")
    transition_id = int(transition_id) if isinstance(transition_id, int) else None

    raw_input = await repo.get_raw_input(task_id=task_id)
    llm_result = await repo.get_latest_llm_result(task_id=task_id)

    chat_id = _extract_chat_id(raw_input or {})
    if chat_id is None or transition_id is None:
        await repo.insert_task_detail(
            task_id=task_id,
            kind="tg_needs_review_notified",
            content={
                "worker": CONSUMER_NAME,
                "transition_id": transition_id,
                "error": "missing chat_id/transition_id",
            },
        )
        await session.commit()
        return True

    llm_request_id = None
    if isinstance(llm_result, dict) and isinstance(llm_result.get("llm_request_id"), int):
        llm_request_id = int(llm_result.get("llm_request_id"))

    llm_response = await repo.get_latest_llm_response_by_request_id(llm_request_id=llm_request_id) if llm_request_id else None
    llm_response_id = llm_response.get("id") if isinstance(llm_response, dict) else None
    llm_response_id = int(llm_response_id) if isinstance(llm_response_id, int) else None
    raw_answer = llm_response.get("answer") if isinstance(llm_response, dict) else None
    answer = _extract_json_answer(raw_answer if isinstance(raw_answer, str) else None)

    llm_error = llm_response.get("error") if isinstance(llm_response, dict) else None
    llm_error = llm_error.strip() if isinstance(llm_error, str) and llm_error.strip() else None

    pr_url = None
    pr_error = None
    job = await repo.get_latest_codegen_job(task_id=task_id)
    if isinstance(job, dict):
        pr_url = job.get("pr_url") if isinstance(job.get("pr_url"), str) and job.get("pr_url").strip() else None
        pr_error = job.get("error") if isinstance(job.get("error"), str) and job.get("error").strip() else None

    msg = _format_needs_review_message(
        task_id=task_id,
        answer=answer,
        llm_error=llm_error,
        pr_url=pr_url,
        pr_error=pr_error,
    )
    try:
        await bot.send_message(chat_id=chat_id, text=msg)
    except Exception as exc:
        logger.warning("Failed to send needs_review for task %s to chat_id=%s: %s", task_id, chat_id, exc)
        await repo.insert_task_detail(
            task_id=task_id,
            kind="tg_needs_review_notified",
            content={
                "worker": CONSUMER_NAME,
                "transition_id": transition_id,
                "llm_request_id": llm_request_id,
                "llm_response_id": llm_response_id,
                "error": str(exc),
            },
        )
        await session.commit()
        return True

    await repo.insert_task_detail(
        task_id=task_id,
        kind="tg_needs_review_notified",
        content={
            "worker": CONSUMER_NAME,
            "transition_id": transition_id,
            "llm_request_id": llm_request_id,
            "llm_response_id": llm_response_id,
        },
    )
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
    waiting_reason = await repo.get_latest_waiting_user_reason(task_id=task_id)

    if not raw_input or (not llm_result and not waiting_reason):
        await repo.insert_task_detail(
            task_id=task_id,
            kind="tg_waiting_user_notified",
            content={"error": "missing raw_input/llm_result/waiting_user_reason", "worker": CONSUMER_NAME},
        )
        await session.commit()
        return True

    chat_id = _extract_chat_id(raw_input)
    question = _extract_clarify_question(llm_result or {}) or _extract_waiting_reason_question(waiting_reason)

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
        logger.warning("Failed to send clarify for task %s to chat_id=%s: %s", task_id, chat_id, exc)
        await repo.insert_task_detail(
            task_id=task_id,
            kind="tg_waiting_user_notified",
            content={"error": str(exc), "worker": CONSUMER_NAME},
        )
        await session.commit()
        return True

    await repo.insert_task_detail(
        task_id=task_id,
        kind="tg_waiting_user_notified",
        content={"worker": CONSUMER_NAME},
    )
    await session.commit()
    return True


async def _process_one_codegen_notify(session: AsyncSession, bot: Bot) -> bool:
    repo = CoreTasksRepository(session)
    task = await repo.pop_one_task_for_codegen_notify()
    if not task:
        return False

    task_id = int(task["id"])
    raw_input = await repo.get_raw_input(task_id=task_id)
    codegen_result = await repo.get_latest_codegen_result(task_id=task_id)

    if not raw_input or not codegen_result:
        await repo.insert_task_detail(
            task_id=task_id,
            kind="tg_codegen_notified",
            content={"error": "missing raw_input/codegen_result", "worker": CONSUMER_NAME},
        )
        await session.commit()
        return True

    chat_id = _extract_chat_id(raw_input)
    if chat_id is None:
        await repo.insert_task_detail(
            task_id=task_id,
            kind="tg_codegen_notified",
            content={"error": "missing chat_id", "worker": CONSUMER_NAME},
        )
        await session.commit()
        return True

    pr_url = codegen_result.get("pr_url") if isinstance(codegen_result.get("pr_url"), str) else None
    repo_full_name = (
        codegen_result.get("repo_full_name") if isinstance(codegen_result.get("repo_full_name"), str) else None
    )
    branch_name = (
        codegen_result.get("branch_name") if isinstance(codegen_result.get("branch_name"), str) else None
    )
    tests_ok = None
    tests = codegen_result.get("tests")
    if isinstance(tests, dict) and isinstance(tests.get("ok"), bool):
        tests_ok = tests.get("ok")

    msg = _format_codegen_message(
        task_id=task_id,
        title=str(task.get("title") or ""),
        pr_url=pr_url,
        tests_ok=tests_ok,
        repo_full_name=repo_full_name,
        branch_name=branch_name,
    )
    try:
        await bot.send_message(chat_id=chat_id, text=msg)
    except Exception as exc:
        logger.warning("Failed to send codegen notify for task %s to chat_id=%s: %s", task_id, chat_id, exc)
        await repo.insert_task_detail(
            task_id=task_id,
            kind="tg_codegen_notified",
            content={"error": str(exc), "worker": CONSUMER_NAME},
        )
        await session.commit()
        return True

    await repo.insert_task_detail(
        task_id=task_id,
        kind="tg_codegen_notified",
        content={"worker": CONSUMER_NAME, "pr_url": pr_url, "tests_ok": tests_ok},
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


async def process_core_codegen_notifications(session: AsyncSession, bot: Bot, *, limit: int = 10) -> int:
    processed = 0
    for _ in range(max(int(limit), 1)):
        if not await _process_one_codegen_notify(session, bot):
            break
        processed += 1
    return processed


async def process_core_needs_review_notifications(session: AsyncSession, bot: Bot, *, limit: int = 10) -> int:
    processed = 0
    for _ in range(max(int(limit), 1)):
        if not await _process_one_needs_review(session, bot):
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

                codegen_processed = await process_core_codegen_notifications(session, bot, limit=10)
                if codegen_processed:
                    logger.info("Sent %s core codegen notifications", codegen_processed)

                needs_review_processed = await process_core_needs_review_notifications(session, bot, limit=10)
                if needs_review_processed:
                    logger.info("Sent %s core needs-review notifications", needs_review_processed)
            except Exception as exc:
                logger.exception("Worker error: %s", exc)
        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_loop())

