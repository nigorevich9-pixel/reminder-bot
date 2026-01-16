from aiogram.dispatcher.middlewares.base import BaseMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker


class DBSessionMiddleware(BaseMiddleware):
    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        super().__init__()
        self._sessionmaker = sessionmaker

    async def __call__(self, handler, event, data):
        async with self._sessionmaker() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
