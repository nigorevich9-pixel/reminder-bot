import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://reminder_user:reminder_pass@localhost:5432/reminder_db",
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    tg_token: str | None = os.getenv("TG_TOKEN")
    tg_api_base: str = os.getenv("TG_API_BASE", "https://api.telegram.org")
    default_timezone: str = os.getenv("DEFAULT_TIMEZONE", "Europe/Moscow")
    worker_poll_seconds: int = int(os.getenv("WORKER_POLL_SECONDS", "5"))

    # Jira integration
    jira_base_url: str = os.getenv("JIRA_BASE_URL", "https://legalbet.atlassian.net")
    jira_email: str | None = os.getenv("JIRA_EMAIL")
    jira_api_token: str | None = os.getenv("JIRA_API_TOKEN")
    jira_poll_seconds: int = int(os.getenv("JIRA_POLL_SECONDS", "120"))  # 2 minutes


settings = Settings()
