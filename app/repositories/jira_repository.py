"""Repository for Jira subscriptions."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JiraLastSeen, JiraSubscription, User


class JiraRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_subscription(
        self, user_id: int, project_key: str, issue_key: str | None = None
    ) -> JiraSubscription | None:
        """Get specific subscription."""
        stmt = select(JiraSubscription).where(
            JiraSubscription.user_id == user_id,
            JiraSubscription.project_key == project_key.upper(),
        )
        if issue_key:
            stmt = stmt.where(JiraSubscription.issue_key == issue_key.upper())
        else:
            stmt = stmt.where(JiraSubscription.issue_key.is_(None))

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_subscriptions(self, user_id: int) -> list[JiraSubscription]:
        """Get all subscriptions for a user."""
        stmt = select(JiraSubscription).where(
            JiraSubscription.user_id == user_id,
            JiraSubscription.is_active,
        ).order_by(JiraSubscription.project_key, JiraSubscription.issue_key)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_active_subscriptions(self) -> list[JiraSubscription]:
        """Get all active subscriptions (for polling worker)."""
        stmt = select(JiraSubscription).where(
            JiraSubscription.is_active
        ).order_by(JiraSubscription.project_key)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_subscriptions_by_project(self, project_key: str) -> list[JiraSubscription]:
        """Get all subscriptions for a project."""
        stmt = select(JiraSubscription).where(
            JiraSubscription.project_key == project_key.upper(),
            JiraSubscription.is_active,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_subscription(
        self,
        user_id: int,
        project_key: str,
        issue_key: str | None = None,
        watch_type: str = "all",
    ) -> JiraSubscription:
        """Create new subscription."""
        sub = JiraSubscription(
            user_id=user_id,
            project_key=project_key.upper(),
            issue_key=issue_key.upper() if issue_key else None,
            watch_type=watch_type,
            is_active=True,
        )
        self.session.add(sub)
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def delete_subscription(self, subscription_id: int) -> bool:
        """Delete subscription by ID."""
        stmt = delete(JiraSubscription).where(JiraSubscription.id == subscription_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def delete_user_subscription(
        self, user_id: int, project_key: str, issue_key: str | None = None
    ) -> bool:
        """Delete specific user subscription."""
        stmt = delete(JiraSubscription).where(
            JiraSubscription.user_id == user_id,
            JiraSubscription.project_key == project_key.upper(),
        )
        if issue_key:
            stmt = stmt.where(JiraSubscription.issue_key == issue_key.upper())
        else:
            stmt = stmt.where(JiraSubscription.issue_key.is_(None))

        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    # Last seen tracking
    async def get_last_seen(self, user_id: int, project_key: str) -> datetime | None:
        """Get last check time for user/project."""
        stmt = select(JiraLastSeen).where(
            JiraLastSeen.user_id == user_id,
            JiraLastSeen.project_key == project_key.upper(),
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        return record.last_checked_at if record else None

    async def update_last_seen(self, user_id: int, project_key: str) -> None:
        """Update last check time for user/project."""
        stmt = select(JiraLastSeen).where(
            JiraLastSeen.user_id == user_id,
            JiraLastSeen.project_key == project_key.upper(),
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()

        now = datetime.now(UTC)
        if record:
            record.last_checked_at = now
        else:
            record = JiraLastSeen(
                user_id=user_id,
                project_key=project_key.upper(),
                last_checked_at=now,
            )
            self.session.add(record)

        await self.session.commit()

    async def get_unique_projects(self) -> list[str]:
        """Get list of unique project keys with active subscriptions."""
        stmt = select(JiraSubscription.project_key).where(
            JiraSubscription.is_active
        ).distinct()
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]

    async def get_subscribers_for_issue(
        self, project_key: str, issue_key: str
    ) -> list[tuple[int, int]]:
        """
        Get list of (user_id, tg_id) who should be notified about this issue.
        Includes both project-wide and issue-specific subscriptions.
        """
        stmt = (
            select(JiraSubscription.user_id, User.tg_id)
            .join(User, User.id == JiraSubscription.user_id)
            .where(
                JiraSubscription.is_active,
                JiraSubscription.project_key == project_key.upper(),
            )
            .where(
                (JiraSubscription.issue_key.is_(None)) |  # project-wide
                (JiraSubscription.issue_key == issue_key.upper())  # specific issue
            )
        )
        result = await self.session.execute(stmt)
        return list(result.all())
