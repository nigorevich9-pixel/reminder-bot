import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.db import AsyncSessionLocal
from app.repositories.core_tasks_repository import CoreTasksRepository


if TYPE_CHECKING:
    from aiogram import Bot
else:
    Bot = object  # type: ignore[misc,assignment]

try:
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError  # type: ignore[import-not-found]

    _PERMANENT_TG_EXC = (TelegramForbiddenError, TelegramBadRequest)
except Exception:
    _PERMANENT_TG_EXC = ()


logger = logging.getLogger("core_task_notify_worker")
CONSUMER_NAME = "reminder_bot_core_task_notify_worker"
UTC = timezone.utc
TG_MESSAGE_VERSION = 1
TG_DELIVERY_MAX_ATTEMPTS = max(int(getattr(settings, "tg_delivery_max_attempts", 10)), 1)
TG_DELIVERY_MAX_RETRY_WINDOW_SECONDS = max(int(getattr(settings, "tg_delivery_max_retry_window_seconds", 86400)), 0)


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

def _format_llm_requeue_message(
    *,
    task_id: int,
    llm_request_id: int | None,
    requeue_count: int | None,
    locked_by: str | None,
    correlation_id: str | None,
) -> str:
    lines = [
        f"task #{task_id}",
        "",
        "LLM: запрос не получил ответ вовремя и переотправлен.",
    ]
    if llm_request_id is not None:
        lines.append(f"llm_request_id: {llm_request_id}")
    if requeue_count is not None:
        lines.append(f"requeue_count: {requeue_count}")
    if locked_by:
        lines.append(f"locked_by: {locked_by}")
    if correlation_id:
        lines.append(f"correlation_id: {correlation_id}")
    return "\n".join(lines).strip()

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

def _format_done_task_message(
    *,
    task_id: int,
    title: str,
    pr_url: str | None,
    tests_ok: bool | None,
    repo_full_name: str | None,
    branch_name: str | None,
) -> str:
    lines = [f"task #{task_id}", f"{title}".strip(), "", "DONE", ""]
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
    elif pr_url:
        lines.append("Tests: (unknown)")
    lines.extend(["", f"Details: /task {task_id}"])
    return "\n".join([l for l in lines if l is not None]).strip()


def _format_failed_message(*, task_id: int, title: str, error: str | None) -> str:
    lines = [f"task #{task_id}", f"{title}".strip(), "", "FAILED"]
    if error:
        lines.extend(["", "error:", str(error).strip()])
    lines.extend(["", f"Details: /task {task_id}"])
    return "\n".join([l for l in lines if l is not None]).strip()


def _format_stopped_message(*, task_id: int, title: str) -> str:
    return "\n".join([f"task #{task_id}", f"{title}".strip(), "", "STOPPED_BY_USER"]).strip()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _delivery_backoff_seconds(attempt_no: int) -> int:
    attempt_no = max(int(attempt_no), 1)
    seq = [10, 30, 120, 300, 900, 3600]
    return int(seq[min(attempt_no - 1, len(seq) - 1)])

def _parse_iso8601_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None

def _should_stop_retrying(*, attempt_no: int, first_attempt_at: datetime | None, now: datetime) -> bool:
    if attempt_no >= TG_DELIVERY_MAX_ATTEMPTS:
        return True
    if TG_DELIVERY_MAX_RETRY_WINDOW_SECONDS <= 0:
        return False
    if first_attempt_at is None:
        return False
    return (now - first_attempt_at).total_seconds() >= TG_DELIVERY_MAX_RETRY_WINDOW_SECONDS

def _classify_send_exception(exc: Exception) -> tuple[bool, str]:
    if _PERMANENT_TG_EXC and isinstance(exc, _PERMANENT_TG_EXC):
        return False, str(exc)
    return True, str(exc)


async def _get_latest_tg_delivery_attempt(
    session: AsyncSession,
    *,
    task_id: int,
    message_kind: str,
    transition_id: int | None = None,
    llm_request_id: int | None = None,
    codegen_detail_id: int | None = None,
) -> dict | None:
    params: dict[str, object] = {
        "task_id": int(task_id),
        "message_kind": str(message_kind),
        "message_version": str(int(TG_MESSAGE_VERSION)),
    }
    where = [
        "task_id = :task_id",
        "kind = 'tg_delivery'",
        "content->>'channel' = 'tg'",
        "content->>'message_kind' = :message_kind",
        "content->>'message_version' = :message_version",
    ]
    if transition_id is not None:
        where.append("CAST(content->>'transition_id' AS int) = :transition_id")
        params["transition_id"] = int(transition_id)
    if llm_request_id is not None:
        where.append("CAST(content->>'llm_request_id' AS int) = :llm_request_id")
        params["llm_request_id"] = int(llm_request_id)
    if codegen_detail_id is not None:
        where.append("CAST(content->>'codegen_detail_id' AS int) = :codegen_detail_id")
        params["codegen_detail_id"] = int(codegen_detail_id)

    sql = (
        "SELECT content "
        "FROM task_details "
        "WHERE " + " AND ".join(where) + " "
        "ORDER BY id DESC LIMIT 1"
    )
    res = await session.execute(sa.text(sql), params)  # type: ignore[name-defined]
    row = res.mappings().first()
    return dict(row["content"]) if row and isinstance(row.get("content"), dict) else None


async def _send_with_tg_delivery_trace(
    session: AsyncSession,
    bot: Bot,
    *,
    task_id: int,
    chat_id: int | None,
    text: str | None,
    message_kind: str,
    to_status: str | None = None,
    transition_id: int | None = None,
    llm_request_id: int | None = None,
    codegen_detail_id: int | None = None,
) -> None:
    repo = CoreTasksRepository(session)

    prev = await _get_latest_tg_delivery_attempt(
        session,
        task_id=task_id,
        message_kind=message_kind,
        transition_id=transition_id,
        llm_request_id=llm_request_id,
        codegen_detail_id=codegen_detail_id,
    )
    prev_attempt_no = prev.get("attempt_no") if isinstance(prev, dict) else None
    prev_attempt_no = int(prev_attempt_no) if isinstance(prev_attempt_no, int) else 0
    attempt_no = prev_attempt_no + 1

    now = _utc_now()
    prev_first_attempt_at = _parse_iso8601_dt(prev.get("first_attempt_at")) if isinstance(prev, dict) else None
    first_attempt_at = prev_first_attempt_at or now
    status = "sent"
    retryable = False
    error = None
    next_attempt_at = None
    telegram_message_id = None

    if chat_id is None or not text:
        status = "failed"
        retryable = False
        error = "missing chat_id/text"
    else:
        try:
            msg = await bot.send_message(chat_id=int(chat_id), text=str(text))
            telegram_message_id = getattr(msg, "message_id", None)
        except Exception as exc:
            status = "failed"
            retryable, error = _classify_send_exception(exc)
            if retryable and _should_stop_retrying(attempt_no=attempt_no, first_attempt_at=first_attempt_at, now=now):
                retryable = False
                error = f"{error} (retry cap reached)"
            if retryable:
                next_attempt_at = (now + timedelta(seconds=_delivery_backoff_seconds(attempt_no))).isoformat()

    await repo.insert_task_detail(
        task_id=int(task_id),
        kind="tg_delivery",
        content={
            "worker": CONSUMER_NAME,
            "channel": "tg",
            "task_id": int(task_id),
            "to_status": str(to_status) if to_status is not None else None,
            "transition_id": int(transition_id) if transition_id is not None else None,
            "llm_request_id": int(llm_request_id) if llm_request_id is not None else None,
            "codegen_detail_id": int(codegen_detail_id) if codegen_detail_id is not None else None,
            "message_kind": str(message_kind),
            "message_version": int(TG_MESSAGE_VERSION),
            "status": status,
            "attempt_no": int(attempt_no),
            "retryable": bool(retryable),
            "error": error,
            "chat_id": int(chat_id) if chat_id is not None else None,
            "telegram_message_id": int(telegram_message_id) if isinstance(telegram_message_id, int) else None,
            "first_attempt_at": first_attempt_at.isoformat(),
            "last_attempt_at": now.isoformat(),
            "next_attempt_at": next_attempt_at,
        },
    )


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
        await _send_with_tg_delivery_trace(
            session,
            bot,
            task_id=task_id,
            chat_id=chat_id,
            text=None,
            message_kind="review_needed",
            to_status=str(task.get("status") or ""),
            transition_id=transition_id,
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
    await _send_with_tg_delivery_trace(
        session,
        bot,
        task_id=task_id,
        chat_id=chat_id,
        text=msg,
        message_kind="review_needed",
        to_status=str(task.get("status") or ""),
        transition_id=transition_id,
    )
    await session.commit()
    return True

async def _process_one_llm_requeue_notify(session: AsyncSession, bot: Bot) -> bool:
    repo = CoreTasksRepository(session)
    task = await repo.pop_one_task_for_llm_requeue_notify()
    if not task:
        return False

    task_id = int(task["id"])
    raw_input = await repo.get_raw_input(task_id=task_id)
    chat_id = _extract_chat_id(raw_input or {})
    requeue_detail = task.get("requeue_detail") if isinstance(task, dict) else None
    requeue_detail = requeue_detail if isinstance(requeue_detail, dict) else {}

    llm_request_id = requeue_detail.get("llm_request_id")
    llm_request_id = int(llm_request_id) if isinstance(llm_request_id, int) else None

    requeue_count = requeue_detail.get("requeue_count")
    requeue_count = int(requeue_count) if isinstance(requeue_count, int) else None

    locked_by = requeue_detail.get("locked_by")
    locked_by = locked_by.strip() if isinstance(locked_by, str) and locked_by.strip() else None

    correlation_id = requeue_detail.get("correlation_id")
    correlation_id = (
        correlation_id.strip() if isinstance(correlation_id, str) and correlation_id.strip() else None
    )

    if chat_id is None or llm_request_id is None:
        await repo.insert_task_detail(
            task_id=task_id,
            kind="tg_llm_requeue_notified",
            content={
                "worker": CONSUMER_NAME,
                "llm_request_id": llm_request_id,
                "error": "missing chat_id/llm_request_id",
            },
        )
        await session.commit()
        return True

    msg = _format_llm_requeue_message(
        task_id=task_id,
        llm_request_id=llm_request_id,
        requeue_count=requeue_count,
        locked_by=locked_by,
        correlation_id=correlation_id,
    )
    try:
        await bot.send_message(chat_id=chat_id, text=msg)
    except Exception as exc:
        logger.warning("Failed to send llm requeue for task %s to chat_id=%s: %s", task_id, chat_id, exc)
        await repo.insert_task_detail(
            task_id=task_id,
            kind="tg_llm_requeue_notified",
            content={
                "worker": CONSUMER_NAME,
                "llm_request_id": llm_request_id,
                "requeue_count": requeue_count,
                "correlation_id": correlation_id,
                "error": str(exc),
            },
        )
        await session.commit()
        return True

    await repo.insert_task_detail(
        task_id=task_id,
        kind="tg_llm_requeue_notified",
        content={
            "worker": CONSUMER_NAME,
            "llm_request_id": llm_request_id,
            "requeue_count": requeue_count,
            "correlation_id": correlation_id,
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
    active_llm_request_id = task.get("active_llm_request_id")
    if isinstance(active_llm_request_id, str) and active_llm_request_id.strip().isdigit():
        active_llm_request_id = int(active_llm_request_id.strip())

    if not raw_input or (not llm_result and not waiting_reason):
        await _send_with_tg_delivery_trace(
            session,
            bot,
            task_id=task_id,
            chat_id=_extract_chat_id(raw_input or {}),
            text=None,
            message_kind="waiting_user",
            to_status=str(task.get("status") or ""),
            llm_request_id=int(active_llm_request_id) if isinstance(active_llm_request_id, int) else None,
        )
        await session.commit()
        return True

    chat_id = _extract_chat_id(raw_input)
    question = _extract_clarify_question(llm_result or {}) or _extract_waiting_reason_question(waiting_reason)

    if chat_id is None or question is None:
        await _send_with_tg_delivery_trace(
            session,
            bot,
            task_id=task_id,
            chat_id=chat_id,
            text=None,
            message_kind="waiting_user",
            to_status=str(task.get("status") or ""),
            llm_request_id=int(active_llm_request_id) if isinstance(active_llm_request_id, int) else None,
        )
        await session.commit()
        return True

    msg = _format_clarify_message(task_id=task_id, question=question)
    await _send_with_tg_delivery_trace(
        session,
        bot,
        task_id=task_id,
        chat_id=chat_id,
        text=msg,
        message_kind="waiting_user",
        to_status=str(task.get("status") or ""),
        llm_request_id=int(active_llm_request_id) if isinstance(active_llm_request_id, int) else None,
    )
    await session.commit()
    return True


async def _process_one_codegen_notify(session: AsyncSession, bot: Bot) -> bool:
    repo = CoreTasksRepository(session)
    task = await repo.pop_one_task_for_codegen_notify()
    if not task:
        return False

    task_id = int(task["id"])
    codegen_detail_id = task.get("codegen_detail_id")
    codegen_detail_id = int(codegen_detail_id) if isinstance(codegen_detail_id, int) else None
    raw_input = await repo.get_raw_input(task_id=task_id)
    codegen_result = await repo.get_latest_codegen_result(task_id=task_id)

    if not raw_input or not codegen_result:
        await _send_with_tg_delivery_trace(
            session,
            bot,
            task_id=task_id,
            chat_id=_extract_chat_id(raw_input or {}),
            text=None,
            message_kind="codegen",
            to_status=str(task.get("status") or ""),
            codegen_detail_id=codegen_detail_id,
        )
        await session.commit()
        return True

    chat_id = _extract_chat_id(raw_input)
    if chat_id is None:
        await _send_with_tg_delivery_trace(
            session,
            bot,
            task_id=task_id,
            chat_id=None,
            text=None,
            message_kind="codegen",
            to_status=str(task.get("status") or ""),
            codegen_detail_id=codegen_detail_id,
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
    await _send_with_tg_delivery_trace(
        session,
        bot,
        task_id=task_id,
        chat_id=chat_id,
        text=msg,
        message_kind="codegen",
        to_status=str(task.get("status") or ""),
        codegen_detail_id=codegen_detail_id,
    )
    await session.commit()
    return True


async def _process_one_done(session: AsyncSession, bot: Bot) -> bool:
    repo = CoreTasksRepository(session)
    task = await repo.pop_one_task_for_done_notify()
    if not task:
        return False

    task_id = int(task["id"])
    transition_id = task.get("transition_id")
    transition_id = int(transition_id) if isinstance(transition_id, int) else None

    raw_input = await repo.get_raw_input(task_id=task_id)
    llm_result = await repo.get_latest_llm_result(task_id=task_id)
    codegen_result = await repo.get_latest_codegen_result(task_id=task_id)

    chat_id = _extract_chat_id(raw_input or {})
    kind = (raw_input or {}).get("kind") if isinstance(raw_input, dict) else None

    msg = None
    if kind == "question":
        question = _extract_question_text(raw_input or {})
        answer = _extract_answer_text(llm_result or {})
        if question and answer:
            msg = _format_message(task_id=task_id, question=question, answer=answer)
    else:
        if isinstance(codegen_result, dict):
            pr_url = codegen_result.get("pr_url") if isinstance(codegen_result.get("pr_url"), str) else None
            repo_full_name = codegen_result.get("repo_full_name") if isinstance(codegen_result.get("repo_full_name"), str) else None
            branch_name = codegen_result.get("branch_name") if isinstance(codegen_result.get("branch_name"), str) else None
            tests_ok = None
            tests = codegen_result.get("tests") if isinstance(codegen_result.get("tests"), dict) else None
            if isinstance(tests, dict) and isinstance(tests.get("ok"), bool):
                tests_ok = bool(tests.get("ok"))
            msg = _format_done_task_message(
                task_id=task_id,
                title=str(task.get("title") or ""),
                pr_url=pr_url,
                tests_ok=tests_ok,
                repo_full_name=repo_full_name,
                branch_name=branch_name,
            )
        else:
            answer = _extract_answer_text(llm_result or {})
            if answer:
                title = str(task.get("title") or "").strip()
                lines = [f"task #{task_id}"]
                if title:
                    lines.append(title)
                lines.extend(["", "DONE", "", "answer:", answer, "", f"Details: /task {task_id}"])
                msg = "\n".join(lines).strip()

    await _send_with_tg_delivery_trace(
        session,
        bot,
        task_id=task_id,
        chat_id=chat_id,
        text=msg,
        message_kind="final",
        to_status=str(task.get("status") or ""),
        transition_id=transition_id,
    )
    await session.commit()
    return True


async def _process_one_failed(session: AsyncSession, bot: Bot) -> bool:
    repo = CoreTasksRepository(session)
    task = await repo.pop_one_task_for_failed_notify()
    if not task:
        return False

    task_id = int(task["id"])
    transition_id = task.get("transition_id")
    transition_id = int(transition_id) if isinstance(transition_id, int) else None

    raw_input = await repo.get_raw_input(task_id=task_id)
    llm_result = await repo.get_latest_llm_result(task_id=task_id)
    job = await repo.get_latest_codegen_job(task_id=task_id)

    chat_id = _extract_chat_id(raw_input or {})
    err = None
    if isinstance(llm_result, dict) and isinstance(llm_result.get("error"), str) and llm_result.get("error").strip():
        err = llm_result.get("error").strip()
    if err is None and isinstance(job, dict) and isinstance(job.get("error"), str) and job.get("error").strip():
        err = job.get("error").strip()

    msg = _format_failed_message(task_id=task_id, title=str(task.get("title") or ""), error=err)
    await _send_with_tg_delivery_trace(
        session,
        bot,
        task_id=task_id,
        chat_id=chat_id,
        text=msg,
        message_kind="failed",
        to_status=str(task.get("status") or ""),
        transition_id=transition_id,
    )
    await session.commit()
    return True


async def _process_one_stopped(session: AsyncSession, bot: Bot) -> bool:
    repo = CoreTasksRepository(session)
    task = await repo.pop_one_task_for_stopped_notify()
    if not task:
        return False

    task_id = int(task["id"])
    transition_id = task.get("transition_id")
    transition_id = int(transition_id) if isinstance(transition_id, int) else None

    raw_input = await repo.get_raw_input(task_id=task_id)
    chat_id = _extract_chat_id(raw_input or {})
    msg = _format_stopped_message(task_id=task_id, title=str(task.get("title") or ""))
    await _send_with_tg_delivery_trace(
        session,
        bot,
        task_id=task_id,
        chat_id=chat_id,
        text=msg,
        message_kind="stopped",
        to_status=str(task.get("status") or ""),
        transition_id=transition_id,
    )
    await session.commit()
    return True


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


async def process_core_done_notifications(session: AsyncSession, bot: Bot, *, limit: int = 10) -> int:
    processed = 0
    for _ in range(max(int(limit), 1)):
        if not await _process_one_done(session, bot):
            break
        processed += 1
    return processed


async def process_core_failed_notifications(session: AsyncSession, bot: Bot, *, limit: int = 10) -> int:
    processed = 0
    for _ in range(max(int(limit), 1)):
        if not await _process_one_failed(session, bot):
            break
        processed += 1
    return processed


async def process_core_stopped_notifications(session: AsyncSession, bot: Bot, *, limit: int = 10) -> int:
    processed = 0
    for _ in range(max(int(limit), 1)):
        if not await _process_one_stopped(session, bot):
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
                clarify_processed = await process_core_waiting_user_notifications(session, bot, limit=10)
                if clarify_processed:
                    logger.info("Sent %s core waiting-user notifications", clarify_processed)

                codegen_processed = await process_core_codegen_notifications(session, bot, limit=10)
                if codegen_processed:
                    logger.info("Sent %s core codegen notifications", codegen_processed)

                needs_review_processed = await process_core_needs_review_notifications(session, bot, limit=10)
                if needs_review_processed:
                    logger.info("Sent %s core needs-review notifications", needs_review_processed)

                done_processed = await process_core_done_notifications(session, bot, limit=10)
                if done_processed:
                    logger.info("Sent %s core done notifications", done_processed)

                failed_processed = await process_core_failed_notifications(session, bot, limit=10)
                if failed_processed:
                    logger.info("Sent %s core failed notifications", failed_processed)

                stopped_processed = await process_core_stopped_notifications(session, bot, limit=10)
                if stopped_processed:
                    logger.info("Sent %s core stopped notifications", stopped_processed)

                requeue_processed = 0
                for _ in range(10):
                    if not await _process_one_llm_requeue_notify(session, bot):
                        break
                    requeue_processed += 1
                if requeue_processed:
                    logger.info("Sent %s core llm-requeue notifications", requeue_processed)
            except Exception as exc:
                logger.exception("Worker error: %s", exc)
        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_loop())

