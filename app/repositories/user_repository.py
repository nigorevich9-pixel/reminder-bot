from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_tg_id(self, tg_id: int) -> User | None:
        result = await self._session.execute(select(User).where(User.tg_id == tg_id))
        return result.scalar_one_or_none()

    async def create(self, *, tg_id: int, username: str | None, first_name: str | None) -> User:
        user = User(tg_id=tg_id, username=username, first_name=first_name)
        self._session.add(user)
        await self._session.flush()
        return user
