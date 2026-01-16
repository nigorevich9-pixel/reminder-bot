"""Jira polling worker - checks for updates and sends notifications."""
import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.db import AsyncSessionLocal
from app.repositories.jira_repository import JiraRepository
from app.services.jira_service import JiraService, format_issue_update


logger = logging.getLogger("jira_worker")


async def check_jira_updates(
    session: AsyncSession,
    bot: Bot,
    lookback_minutes: int,
) -> int:
    """Check for Jira updates and notify subscribers."""
    repo = JiraRepository(session)
    
    # Get all unique projects with active subscriptions
    projects = await repo.get_unique_projects()
    if not projects:
        return 0
    
    jira = JiraService()
    notified = 0
    
    # Check each project
    lookback_minutes = max(lookback_minutes, 3)  # At least 3 minutes lookback

    try:
        issues = await jira.get_recently_updated_issues(projects, minutes=lookback_minutes)
    except Exception as e:
        logger.error("Failed to fetch Jira updates: %s", e)
        return 0
    
    if not issues:
        return 0
    
    logger.info("Found %d updated issues in projects %s", len(issues), projects)
    
    # For each updated issue, find subscribers and notify
    for issue in issues:
        key = issue.get("key", "")
        if not key:
            continue
        
        project_key = key.split("-")[0] if "-" in key else key
        
        # Get subscribers for this issue
        subscribers = await repo.get_subscribers_for_issue(project_key, key)
        if not subscribers:
            continue
        
        # Get changelog for more details (optional, can be slow)
        try:
            since = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
            changes = await jira.get_issue_changelog(key, since=since)
        except Exception:
            changes = None
        
        # Format message
        message = format_issue_update(issue, changes)
        
        # Notify each subscriber
        for user_id, tg_id in subscribers:
            try:
                await bot.send_message(
                    chat_id=tg_id,
                    text=message,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                notified += 1
                logger.debug("Notified user %d about %s", tg_id, key)
            except Exception as e:
                logger.warning("Failed to notify user %d about %s: %s", tg_id, key, e)
    
    return notified


def _seconds_until_next_run(now_local: datetime) -> int:
    """Sleep until next allowed polling window (09:00 local)."""
    next_day = now_local
    if now_local.hour >= 19:
        next_day = now_local + timedelta(days=1)
    target = datetime.combine(next_day.date(), time(9, 0), tzinfo=now_local.tzinfo)
    if target <= now_local:
        target = target + timedelta(days=1)
    return max(int((target - now_local).total_seconds()), 60)


async def run_jira_loop() -> None:
    """Main loop for Jira polling."""
    if not settings.tg_token:
        raise RuntimeError("TG_TOKEN is not set")
    
    if not settings.jira_email or not settings.jira_api_token:
        logger.warning("Jira not configured (JIRA_EMAIL/JIRA_API_TOKEN missing), worker disabled")
        return
    
    # Test connection on startup
    try:
        jira = JiraService()
        user = await jira.get_current_user()
        logger.info("Jira connected as: %s", user.get("displayName", "Unknown"))
    except Exception as e:
        logger.error("Failed to connect to Jira: %s", e)
        return
    
    bot = Bot(token=settings.tg_token)
    poll_seconds = settings.jira_poll_seconds
    tz = ZoneInfo(settings.default_timezone)
    last_catchup_date: datetime.date | None = None

    logger.info("Jira worker started, polling every %d seconds", poll_seconds)

    while True:
        now_local = datetime.now(tz)
        # Stop polling after 19:00, resume at 09:00 next day
        if now_local.hour >= 19 or now_local.hour < 9:
            sleep_seconds = _seconds_until_next_run(now_local)
            logger.info(
                "Outside working hours (09:00-19:00). Sleeping for %ds",
                sleep_seconds,
            )
            await asyncio.sleep(sleep_seconds)
            continue

        # Morning catch-up: check changes from 19:00 yesterday to 09:00 today
        if last_catchup_date != now_local.date():
            catchup_minutes = 14 * 60  # 19:00 -> 09:00 = 14 hours
            async with AsyncSessionLocal() as session:
                try:
                    notified = await check_jira_updates(session, bot, catchup_minutes)
                    if notified:
                        logger.info("Sent %d Jira notifications (morning catch-up)", notified)
                except Exception as e:
                    logger.exception("Jira worker error (catch-up): %s", e)
            last_catchup_date = now_local.date()

        async with AsyncSessionLocal() as session:
            try:
                lookback_minutes = max(poll_seconds // 60 + 1, 3)
                notified = await check_jira_updates(session, bot, lookback_minutes)
                if notified:
                    logger.info("Sent %d Jira notifications", notified)
            except Exception as e:
                logger.exception("Jira worker error: %s", e)

        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(run_jira_loop())
