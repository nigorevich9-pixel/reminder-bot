import asyncio
import json
import logging
import os
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
    from aiogram.types import BufferedInputFile  # type: ignore[import-not-found]
except Exception:
    BufferedInputFile = None

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
TG_TEXT_MAX_CHARS = 3800


def _env_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name, "") or "").strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _tg_text_max_chars() -> int:
    return max(_env_int("TG_TEXT_MAX_CHARS", TG_TEXT_MAX_CHARS), 200)


def _truncate_tg_text(*, task_id: int, text: str) -> str:
    t = str(text or "")
    max_chars = _tg_text_max_chars()
    if len(t) <= max_chars:
        return t
    suffix = f"\n\n…(truncated; Details: /task {int(task_id)})"
    cut = max(max_chars - len(suffix), 0)
    return (t[:cut].rstrip() + suffix).strip()


def _extract_chat_id(raw_input: dict) -> int | None:
    tg = raw_input.get("tg")
    if not isinstance(tg, dict):
        return None
    chat_id = tg.get("chat_id")
    return int(chat_id) if isinstance(chat_id, int) and chat_id else None


def _extract_question_text(raw_input: dict) -> str | None:
    text = raw_input.get("text")
    if not (isinstance(text, str) and text.strip()):
        req = raw_input.get("request")
        if isinstance(req, dict):
            text = req.get("text")
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

def _format_answer_only_message(*, task_id: int, answer: str) -> str:
    return f"task #{task_id}\n\nОтвет:\n{answer}"

def _format_done_fallback_message(*, task_id: int, title: str | None = None) -> str:
    title = (title or "").strip()
    lines = [f"task #{task_id}"]
    if title:
        lines.append(title)
    lines.extend(["", "DONE", "", f"Details: /task {task_id}"])
    return "\n".join(lines).strip()


def _format_clarify_message(*, task_id: int, question: str) -> str:
    return (
        f"task #{task_id}\n\n"
        f"Нужно уточнение:\n{question}\n\n"
        f"Ответь командой:\n/ask {task_id} <твой ответ>"
    )


def _safe_filename_piece(s: str) -> str:
    raw = str(s or "").strip()
    if not raw:
        return "file"
    out = []
    for ch in raw:
        if ch.isalnum():
            out.append(ch)
        elif ch in {"-", "_", "."}:
            out.append(ch)
        else:
            out.append("_")
    s2 = "".join(out).strip("._")
    return s2[:80] if s2 else "file"


def _format_read_file_paging_message(*, task_id: int, path: str, part_no: int) -> str:
    p = _safe_filename_piece(path)
    return (
        f"task #{task_id}\n\n"
        f"Файл большой: {p}\n"
        f"Часть: {int(part_no)}\n\n"
        f"Следующая часть:\n/ask {task_id} next\n\n"
        f"Весь файл одним .txt:\n/ask {task_id} all\n\n"
        f"Details: /task {task_id}"
    ).strip()


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


def _document_bytes_from_answer(answer_raw: str) -> tuple[str, bytes]:
    raw_no_fences = _strip_markdown_fences(answer_raw)
    head = raw_no_fences.lstrip()
    ext = "json" if (head.startswith("{") or head.startswith("[")) else "txt"
    if ext == "json":
        try:
            obj = json.loads(head)
            pretty = json.dumps(obj, ensure_ascii=False, indent=2).rstrip() + "\n"
            return ext, pretty.encode("utf-8", errors="replace")
        except Exception:
            pass
    return ext, raw_no_fences.encode("utf-8", errors="replace")

def _pretty_json_no_prune(text: str | None) -> str | None:
    if not isinstance(text, str):
        return text
    raw = _strip_markdown_fences(text)
    if not raw or not (raw.startswith("{") or raw.startswith("[")):
        return text
    try:
        obj = json.loads(raw)
    except Exception:
        return text
    if not isinstance(obj, (dict, list)):
        return text
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return text


def _maybe_pretty_json_for_tg(text: str | None) -> str | None:
    if not isinstance(text, str):
        return text
    raw = _strip_markdown_fences(text)
    if not raw or not (raw.startswith("{") or raw.startswith("[")):
        return text
    try:
        obj = json.loads(raw)
    except Exception:
        return text
    if not isinstance(obj, (dict, list)):
        return text

    # Always keep content intact by default. If Telegram text limits are hit,
    # we rely on the normal truncation / file-delivery path instead.
    prune_enabled = bool(_env_int("TG_PRETTY_JSON_PRUNE", 0))
    if not prune_enabled:
        try:
            return json.dumps(obj, ensure_ascii=False, indent=2)
        except Exception:
            return text

    max_depth = max(_env_int("TG_PRETTY_JSON_MAX_DEPTH", 4), 1)
    max_items = max(_env_int("TG_PRETTY_JSON_MAX_ITEMS", 30), 1)
    max_str = max(_env_int("TG_PRETTY_JSON_MAX_STRING", 400), 50)

    def _clip_str(s: str) -> str:
        s2 = s if isinstance(s, str) else str(s)
        if len(s2) <= max_str:
            return s2
        return s2[: max_str - 3] + "..."

    def _prune(x: object, depth: int) -> object:
        if depth <= 0:
            return "…"
        if isinstance(x, str):
            return _clip_str(x)
        if isinstance(x, dict):
            out: dict[str, object] = {}
            items = list(x.items())
            for k, v in items[:max_items]:
                out[_clip_str(str(k))] = _prune(v, depth - 1)
            if len(items) > max_items:
                out["…"] = f"+{len(items) - max_items} keys"
            return out
        if isinstance(x, list):
            out_list: list[object] = []
            for v in x[:max_items]:
                out_list.append(_prune(v, depth - 1))
            if len(x) > max_items:
                out_list.append(f"… +{len(x) - max_items} items")
            return out_list
        if isinstance(x, (int, float, bool)) or x is None:
            return x
        return _clip_str(str(x))

    pruned = _prune(obj, max_depth)
    try:
        return json.dumps(pruned, ensure_ascii=False, indent=2)
    except Exception:
        return text

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
    document: tuple[str, bytes] | None = None,
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
    sent_as = None
    document_filename = None

    if chat_id is None or (not text and not document):
        status = "failed"
        retryable = False
        error = "missing chat_id/text"
    else:
        try:
            if document is not None and hasattr(bot, "send_document"):
                filename, b = document
                document_filename = str(filename or "result.json")
                if BufferedInputFile is not None:
                    input_file = BufferedInputFile(b, filename=document_filename)  # type: ignore[call-arg]
                else:
                    class _BytesFile:
                        def __init__(self, data: bytes, filename: str) -> None:
                            self.data = data
                            self.filename = filename

                    input_file = _BytesFile(b, document_filename)
                caption = _truncate_tg_text(task_id=task_id, text=str(text or ""))
                msg = await bot.send_document(chat_id=int(chat_id), document=input_file, caption=caption)  # type: ignore[attr-defined]
                telegram_message_id = getattr(msg, "message_id", None)
                sent_as = "document"
            else:
                safe_text = _truncate_tg_text(task_id=task_id, text=str(text or ""))
                msg = await bot.send_message(chat_id=int(chat_id), text=safe_text)
                telegram_message_id = getattr(msg, "message_id", None)
                sent_as = "message"
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
            "sent_as": sent_as,
            "document_filename": document_filename,
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

    answer_raw = answer
    answer_for_msg = _pretty_json_no_prune(answer_raw) if isinstance(answer_raw, str) else answer_raw
    msg = _format_needs_review_message(
        task_id=task_id,
        answer=answer_for_msg,
        llm_error=llm_error,
        pr_url=pr_url,
        pr_error=pr_error,
    )
    document = None
    if isinstance(answer_raw, str) and len(msg or "") > _tg_text_max_chars():
        ext, b = _document_bytes_from_answer(answer_raw)
        filename = f"task_{task_id}_answer.{ext}"
        document = (filename, b)
        msg = _format_needs_review_message(
            task_id=task_id,
            answer=f"(Приложено файлом: {filename})",
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
        document=document,
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
    answer = _extract_answer_text(llm_result or {})

    if chat_id is None or (question is None and answer is None):
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

    msg = None
    document = None
    if question is not None:
        msg = _format_clarify_message(task_id=task_id, question=question)
    elif isinstance(waiting_reason, dict) and waiting_reason.get("type") == "read_file_paging" and answer is not None:
        part_no = waiting_reason.get("part_no") if isinstance(waiting_reason.get("part_no"), int) else 1
        path = waiting_reason.get("path") if isinstance(waiting_reason.get("path"), str) else "file"
        msg = _format_read_file_paging_message(task_id=task_id, path=path, part_no=int(part_no))
        filename = f"task_{task_id}_{_safe_filename_piece(path)}_part{int(part_no)}.txt"
        document = (filename, answer.encode("utf-8", errors="replace"))
    elif answer is not None:
        msg = _format_answer_only_message(task_id=task_id, answer=answer)

    await _send_with_tg_delivery_trace(
        session,
        bot,
        task_id=task_id,
        chat_id=chat_id,
        text=msg,
        document=document,
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
    document = None
    if kind == "question":
        question = _extract_question_text(raw_input or {})
        answer = await repo.get_latest_llm_answer(task_id=task_id)
        if answer is None:
            answer = _extract_answer_text(llm_result or {})
        answer_raw = answer
        answer_for_msg = _pretty_json_no_prune(answer_raw) if isinstance(answer_raw, str) else answer_raw
        answer = answer_for_msg
        if answer:
            if question:
                msg = _format_message(task_id=task_id, question=question, answer=answer)
            else:
                msg = _format_answer_only_message(task_id=task_id, answer=answer)
            if isinstance(answer_raw, str) and len(msg or "") > _tg_text_max_chars():
                ext, b = _document_bytes_from_answer(answer_raw)
                filename = f"task_{task_id}_answer.{ext}"
                document = (filename, b)
                placeholder = f"(Приложено файлом: {filename})"
                if question:
                    msg = _format_message(task_id=task_id, question=question, answer=placeholder)
                else:
                    msg = _format_answer_only_message(task_id=task_id, answer=placeholder)
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
            answer_raw = answer
            answer_for_msg = _pretty_json_no_prune(answer_raw) if isinstance(answer_raw, str) else answer_raw
            answer = answer_for_msg
            if answer:
                title = str(task.get("title") or "").strip()
                lines = [f"task #{task_id}"]
                if title:
                    lines.append(title)
                lines.extend(["", "DONE", "", "answer:", answer, "", f"Details: /task {task_id}"])
                msg = "\n".join(lines).strip()
                if isinstance(answer_raw, str) and len(msg or "") > _tg_text_max_chars():
                    ext, b = _document_bytes_from_answer(answer_raw)
                    filename = f"task_{task_id}_answer.{ext}"
                    document = (filename, b)
                    lines2 = [f"task #{task_id}"]
                    if title:
                        lines2.append(title)
                    lines2.extend(["", "DONE", "", "answer:", f"(Приложено файлом: {filename})", "", f"Details: /task {task_id}"])
                    msg = "\n".join(lines2).strip()
    if not msg:
        msg = _format_done_fallback_message(task_id=task_id, title=str(task.get("title") or ""))

    await _send_with_tg_delivery_trace(
        session,
        bot,
        task_id=task_id,
        chat_id=chat_id,
        text=msg,
        document=document,
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

