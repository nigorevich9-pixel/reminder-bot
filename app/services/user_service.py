from app.repositories.user_repository import UserRepository


class UserService:
    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    async def get_or_create(self, tg_id: int, username: str | None, first_name: str | None):
        user = await self._repo.get_by_tg_id(tg_id)
        if user:
            return user
        return await self._repo.create(tg_id=tg_id, username=username, first_name=first_name)
