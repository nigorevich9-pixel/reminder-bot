from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Reminder, User


class ReminderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: int) -> list[Reminder]:
        result = await self._session.execute(
            select(Reminder).where(Reminder.user_id ==
                                   user_id).order_by(Reminder.next_run_at)
        )
        return list(result.scalars().all())

    async def list_next_days(self, user_id: int, until_dt: datetime) -> list[Reminder]:
        result = await self._session.execute(
            select(Reminder)
            .where(Reminder.user_id == user_id)
            .where(Reminder.next_run_at.is_not(None))
            .where(Reminder.next_run_at <= until_dt)
            .order_by(Reminder.next_run_at)
        )
        return list(result.scalars().all())

    async def list_due(
        self, since_dt: datetime, until_dt: datetime, limit: int = 100
    ) -> list[Reminder]:
        result = await self._session.execute(
            select(Reminder)
            .join(User, User.id == Reminder.user_id)
            .options(selectinload(Reminder.user))
            .where(Reminder.status == "active")
            .where(Reminder.next_run_at.is_not(None))
            .where(Reminder.next_run_at >= since_dt)
            .where(Reminder.next_run_at <= until_dt)
            .order_by(Reminder.next_run_at)
            .limit(limit)
        )
        return list(result.scalars().all())

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
        next_run_at: datetime | None,
    ) -> Reminder:
        reminder = Reminder(
            user_id=user_id,
            title=title,
            message=message,
            reminder_type=reminder_type,
            run_at=run_at,
            cron_expr=cron_expr,
            timezone=timezone,
            next_run_at=next_run_at,
            status="active",
        )
        self._session.add(reminder)
        await self._session.flush()
        return reminder
