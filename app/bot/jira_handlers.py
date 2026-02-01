"""Jira subscription handlers for Telegram bot."""
import re

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.repositories.jira_repository import JiraRepository
from app.repositories.user_repository import UserRepository
from app.services.jira_service import JiraService
from app.services.user_service import UserService


router = Router()


async def _get_or_create_user(session: AsyncSession, message: Message):
    repo = UserRepository(session)
    service = UserService(repo)
    return await service.get_or_create(
        tg_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )


def _parse_jira_key(text: str) -> tuple[str, str | None]:
    """
    Parse Jira key from text.
    Returns (project_key, issue_key or None)

    Examples:
        "PMD" -> ("PMD", None)
        "PMD-7742" -> ("PMD", "PMD-7742")
    """
    text = text.strip().upper()

    # Issue key pattern: PROJECT-NUMBER
    issue_match = re.match(r"^([A-Z][A-Z0-9]+)-(\d+)$", text)
    if issue_match:
        project = issue_match.group(1)
        return project, text

    # Project key only: PROJECT
    project_match = re.match(r"^[A-Z][A-Z0-9]+$", text)
    if project_match:
        return text, None

    raise ValueError(f"Invalid Jira key format: {text}")


@router.message(Command("jira"))
async def jira_help_handler(message: Message):
    """Show Jira commands help."""
    await message.answer(
        "🎫 <b>Jira интеграция</b>\n\n"
        "<b>Команды:</b>\n"
        "/jira_watch &lt;PROJECT&gt; — подписаться на проект\n"
        "/jira_watch &lt;PMD-7742&gt; — подписаться на задачу\n"
        "/jira_unwatch &lt;PROJECT|ISSUE&gt; — отписаться\n"
        "/jira_list — мои подписки\n"
        "/jira_test — проверить подключение\n\n"
        "<b>Примеры:</b>\n"
        "<code>/jira_watch PMD</code> — все изменения в проекте PMD\n"
        "<code>/jira_watch PMD-7742</code> — только задача PMD-7742",
        parse_mode="HTML",
    )


@router.message(Command("jira_test"))
async def jira_test_handler(message: Message):
    """Test Jira connection."""
    if not settings.jira_email or not settings.jira_api_token:
        await message.answer(
            "❌ Jira не настроена.\n"
            "Установи JIRA_EMAIL и JIRA_API_TOKEN в .env"
        )
        return

    try:
        jira = JiraService()
        user_info = await jira.get_current_user()
        display_name = user_info.get("displayName", "Unknown")
        email = user_info.get("emailAddress", "")
        await message.answer(
            f"✅ Подключение к Jira успешно!\n\n"
            f"👤 <b>{display_name}</b>\n"
            f"📧 {email}\n"
            f"🔗 {settings.jira_base_url}",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка подключения к Jira:\n<code>{e}</code>", parse_mode="HTML")


@router.message(Command("jira_watch"))
async def jira_watch_handler(message: Message, session: AsyncSession):
    """Subscribe to Jira project or issue."""
    user = await _get_or_create_user(session, message)

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "Использование:\n"
            "<code>/jira_watch PMD</code> — весь проект\n"
            "<code>/jira_watch PMD-7742</code> — конкретная задача",
            parse_mode="HTML",
        )
        return

    try:
        project_key, issue_key = _parse_jira_key(args[1])
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return

    repo = JiraRepository(session)

    # Check if already subscribed
    existing = await repo.get_subscription(user.id, project_key, issue_key)
    if existing:
        target = issue_key or project_key
        await message.answer(f"⚠️ Ты уже подписан на <b>{target}</b>", parse_mode="HTML")
        return

    # Create subscription
    await repo.create_subscription(user.id, project_key, issue_key)

    if issue_key:
        await message.answer(
            f"✅ Подписка на задачу <b>{issue_key}</b> создана!\n"
            f"Ты будешь получать уведомления об изменениях.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"✅ Подписка на проект <b>{project_key}</b> создана!\n"
            f"Ты будешь получать уведомления обо всех изменениях в проекте.",
            parse_mode="HTML",
        )


@router.message(Command("jira_unwatch"))
async def jira_unwatch_handler(message: Message, session: AsyncSession):
    """Unsubscribe from Jira project or issue."""
    user = await _get_or_create_user(session, message)

    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "Использование:\n"
            "<code>/jira_unwatch PMD</code> — отписаться от проекта\n"
            "<code>/jira_unwatch PMD-7742</code> — отписаться от задачи",
            parse_mode="HTML",
        )
        return

    try:
        project_key, issue_key = _parse_jira_key(args[1])
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return

    repo = JiraRepository(session)
    deleted = await repo.delete_user_subscription(user.id, project_key, issue_key)

    target = issue_key or project_key
    if deleted:
        await message.answer(f"✅ Подписка на <b>{target}</b> удалена.", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ Подписка на <b>{target}</b> не найдена.", parse_mode="HTML")


@router.message(Command("jira_list"))
async def jira_list_handler(message: Message, session: AsyncSession):
    """List user's Jira subscriptions."""
    user = await _get_or_create_user(session, message)
    repo = JiraRepository(session)

    subs = await repo.get_user_subscriptions(user.id)

    if not subs:
        await message.answer(
            "📋 У тебя нет подписок на Jira.\n\n"
            "Используй /jira_watch для подписки на проект или задачу."
        )
        return

    lines = ["📋 <b>Твои подписки на Jira:</b>\n"]

    current_project = None
    for sub in subs:
        if sub.project_key != current_project:
            current_project = sub.project_key
            lines.append(f"\n🗂 <b>{current_project}</b>")

        if sub.issue_key:
            link = f"{settings.jira_base_url}/browse/{sub.issue_key}"
            lines.append(f"  • <a href='{link}'>{sub.issue_key}</a>")
        else:
            lines.append("  • Весь проект")

    lines.append("\n\nИспользуй /jira_unwatch для отписки.")

    await message.answer("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)


@router.message(Command("jira_check"))
async def jira_check_handler(message: Message, session: AsyncSession):
    """Manually check for Jira updates (for debugging)."""
    user = await _get_or_create_user(session, message)
    repo = JiraRepository(session)

    subs = await repo.get_user_subscriptions(user.id)
    if not subs:
        await message.answer("У тебя нет подписок.")
        return

    if not settings.jira_email or not settings.jira_api_token:
        await message.answer("❌ Jira не настроена.")
        return

    try:
        jira = JiraService()
        projects = list({s.project_key for s in subs})
        issues = await jira.get_recently_updated_issues(projects, minutes=60)

        if not issues:
            await message.answer("📭 Нет обновлений за последний час.")
            return

        lines = [f"📬 <b>Обновления за последний час ({len(issues)}):</b>\n"]
        for issue in issues[:10]:  # Limit to 10
            key = issue.get("key", "???")
            fields = issue.get("fields", {})
            summary = fields.get("summary", "")[:50]
            status = fields.get("status", {}).get("name", "?")
            link = f"{settings.jira_base_url}/browse/{key}"
            lines.append(f"• <a href='{link}'>{key}</a> [{status}] {summary}")

        if len(issues) > 10:
            lines.append(f"\n... и ещё {len(issues) - 10} задач")

        await message.answer("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)

    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
