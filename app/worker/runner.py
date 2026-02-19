import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.db import AsyncSessionLocal
from app.repositories.reminder_repository import ReminderRepository
from app.worker.core_task_notify_worker import (
    process_core_codegen_notifications,
    process_core_done_notifications,
    process_core_failed_notifications,
    process_core_needs_review_notifications,
    process_core_stopped_notifications,
    process_core_waiting_user_notifications,
)
from app.utils.datetime import compute_next_run_at


logger = logging.getLogger("reminder_worker")
UTC = timezone.utc


async def process_due_reminders(session: AsyncSession, bot: Bot) -> int:
    repo = ReminderRepository(session)
    now_utc = datetime.now(UTC)
    since_utc = now_utc - timedelta(hours=1)
    due = await repo.list_due(since_utc, now_utc, limit=100)
    if not due:
        return 0

    processed = 0
    for reminder in due:
        if reminder.user is None:
            continue
        text = reminder.message or reminder.title
        try:
            await bot.send_message(chat_id=reminder.user.tg_id, text=text)
        except Exception as exc:
            logger.warning("Failed to send reminder %s: %s", reminder.id, exc)
            continue

        if reminder.reminder_type == "one_time":
            reminder.status = "done"
            reminder.next_run_at = None
        else:
            reminder.next_run_at = compute_next_run_at(
                reminder.reminder_type,
                reminder.run_at,
                reminder.timezone,
                reminder.cron_expr,
            )
        processed += 1

    await session.commit()
    return processed


async def run_loop() -> None:
    if not settings.tg_token:
        raise RuntimeError("TG_TOKEN is not set")

    bot = Bot(token=settings.tg_token)
    while True:
        async with AsyncSessionLocal() as session:
            try:
                processed = await process_due_reminders(session, bot)
                if processed:
                    logger.info("Processed %s reminders", processed)
                asked = await process_core_waiting_user_notifications(session, bot, limit=20)
                if asked:
                    logger.info("Sent %s core waiting-user notifications", asked)
                needs_review = await process_core_needs_review_notifications(session, bot, limit=20)
                if needs_review:
                    logger.info("Sent %s core needs-review notifications", needs_review)
                codegen_notified = await process_core_codegen_notifications(session, bot, limit=20)
                if codegen_notified:
                    logger.info("Sent %s core codegen notifications", codegen_notified)
                done_notified = await process_core_done_notifications(session, bot, limit=20)
                if done_notified:
                    logger.info("Sent %s core done notifications", done_notified)
                failed_notified = await process_core_failed_notifications(session, bot, limit=20)
                if failed_notified:
                    logger.info("Sent %s core failed notifications", failed_notified)
                stopped_notified = await process_core_stopped_notifications(session, bot, limit=20)
                if stopped_notified:
                    logger.info("Sent %s core stopped notifications", stopped_notified)
            except Exception as exc:
                logger.exception("Worker error: %s", exc)
        await asyncio.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_loop())
