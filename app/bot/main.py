import asyncio

from aiogram import Bot, Dispatcher

from app.bot.handlers import router
from app.bot.middlewares import DBSessionMiddleware
from app.config.settings import settings
from app.db import AsyncSessionLocal


# Optional Jira integration (separate feature)
try:
    from app.bot.jira_handlers import router as jira_router
    HAS_JIRA = True
except ImportError:
    HAS_JIRA = False


async def main() -> None:
    if not settings.tg_token:
        raise RuntimeError("TG_TOKEN is not set")
    bot = Bot(token=settings.tg_token)
    dp = Dispatcher()
    dp.update.middleware(DBSessionMiddleware(AsyncSessionLocal))
    dp.include_router(router)
    if HAS_JIRA:
        dp.include_router(jira_router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
