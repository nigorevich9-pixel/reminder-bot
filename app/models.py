from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    reminders: Mapped[list[Reminder]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    jira_subscriptions: Mapped[list[JiraSubscription]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str | None] = mapped_column(Text)
    reminder_type: Mapped[str] = mapped_column(String(32))  # one_time/daily/weekly/monthly/cron
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cron_expr: Mapped[str | None] = mapped_column(String(120))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="reminders")


Index("idx_reminders_user_next", Reminder.user_id, Reminder.next_run_at)


class JiraSubscription(Base):
    """User subscription to Jira project/issue updates."""
    __tablename__ = "jira_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    project_key: Mapped[str] = mapped_column(String(32), index=True)  # e.g. "PMD"
    issue_key: Mapped[str | None] = mapped_column(String(64))  # specific issue, e.g. "PMD-7742"
    watch_type: Mapped[str] = mapped_column(String(32), default="all")  # all/status/assignee/comment
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="jira_subscriptions")

    __table_args__ = (
        Index("idx_jira_sub_user_project", user_id, project_key),
    )


class JiraLastSeen(Base):
    """Track last seen update time per project to avoid duplicate notifications."""
    __tablename__ = "jira_last_seen"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    project_key: Mapped[str] = mapped_column(String(32))
    last_checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship()

    __table_args__ = (
        Index("idx_jira_lastseen_user_project", user_id, project_key, unique=True),
    )
