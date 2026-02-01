from datetime import datetime, timezone


UTC = timezone.utc

def utc_now() -> datetime:
    return datetime.now(UTC)
