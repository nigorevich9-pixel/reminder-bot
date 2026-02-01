from datetime import UTC, datetime, timedelta

from app.repositories.reminder_repository import ReminderRepository
from app.utils.datetime import compute_next_run_at


class ReminderService:
    def __init__(self, repo: ReminderRepository) -> None:
        self._repo = repo

    async def list_all(self, user_id: int):
        return await self._repo.list_by_user(user_id)

    async def list_next_days(self, user_id: int, days: int = 7):
        until_dt = datetime.now(UTC) + timedelta(days=days)
        return await self._repo.list_next_days(user_id, until_dt)

    async def create(
        self,
        *,
        user_id: int,
        title: str,
        message: str | None,
        reminder_type: str,
        run_at: datetime | None,
        cron_expr: str | None,
        timezone: str,
    ):
        next_run_at = compute_next_run_at(reminder_type, run_at, timezone, cron_expr)
        return await self._repo.create(
            user_id=user_id,
            title=title,
            message=message,
            reminder_type=reminder_type,
            run_at=run_at,
            cron_expr=cron_expr,
            timezone=timezone,
            next_run_at=next_run_at,
        )

    async def get_by_id_for_user(self, reminder_id: int, user_id: int):
        return await self._repo.get_by_id_for_user(reminder_id, user_id)

    async def update(
        self,
        *,
        reminder,
        title: str,
        message: str | None,
        reminder_type: str,
        run_at: datetime | None,
        cron_expr: str | None,
        timezone: str,
    ):
        next_run_at = compute_next_run_at(reminder_type, run_at, timezone, cron_expr)
        return await self._repo.update(
            reminder,
            title=title,
            message=message,
            reminder_type=reminder_type,
            run_at=run_at,
            cron_expr=cron_expr,
            timezone=timezone,
            next_run_at=next_run_at,
        )

    async def mark_done(self, reminder):
        return await self._repo.mark_done(reminder)

    async def delete(self, reminder):
        await self._repo.delete(reminder)
