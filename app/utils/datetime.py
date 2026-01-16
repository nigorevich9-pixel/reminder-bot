from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from croniter import croniter


def parse_user_datetime(value: str, tz_name: str) -> datetime:
    tz = ZoneInfo(tz_name)
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            local_dt = datetime.strptime(value.strip(), fmt).replace(tzinfo=tz)
            return local_dt.astimezone(timezone.utc)
        except ValueError:
            continue
    raise ValueError("Invalid datetime format")


def parse_user_date(value: str) -> datetime.date:
    raw = value.strip()
    for fmt in ("%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    parts = raw.split()
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        day = int(parts[0])
        month = int(parts[1])
        year = int(parts[2])
        try:
            return datetime.strptime(f"{day:02d}-{month:02d}-{year:04d}", "%d-%m-%Y").date()
        except ValueError:
            pass
    raise ValueError("Invalid date format")


def parse_user_time(value: str) -> datetime.time:
    raw = value.strip()
    if ":" in raw:
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                return datetime.strptime(raw, fmt).time()
            except ValueError:
                continue
    parts = raw.split()
    if len(parts) == 2 and all(p.isdigit() for p in parts):
        hour = int(parts[0])
        minute = int(parts[1])
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()
    raise ValueError("Invalid time format")


def build_user_datetime(date_value: str, time_value: str, tz_name: str) -> datetime:
    tz = ZoneInfo(tz_name)
    date_part = parse_user_date(date_value)
    time_part = parse_user_time(time_value)
    local_dt = datetime.combine(date_part, time_part).replace(tzinfo=tz)
    return local_dt.astimezone(timezone.utc)


def format_user_datetime(value: datetime | None, tz_name: str) -> str:
    if value is None:
        return "-"
    tz = ZoneInfo(tz_name)
    local_dt = value.astimezone(tz)
    return local_dt.strftime("%Y-%m-%d %H:%M")


def compute_next_run_at(
    reminder_type: str,
    run_at_utc: datetime | None,
    tz_name: str,
    cron_expr: str | None,
) -> datetime | None:
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)

    if reminder_type == "cron":
        if not cron_expr:
            raise ValueError("cron_expr is required for cron reminders")
        next_dt = croniter(cron_expr, now_local).get_next(datetime)
        if next_dt.tzinfo is None:
            next_dt = next_dt.replace(tzinfo=tz)
        return next_dt.astimezone(timezone.utc)

    if run_at_utc is None:
        raise ValueError("run_at is required for non-cron reminders")

    run_local = run_at_utc.astimezone(tz)
    if reminder_type == "one_time":
        return run_local.astimezone(timezone.utc)

    next_local = run_local
    while next_local <= now_local:
        if reminder_type == "daily":
            next_local = next_local + timedelta(days=1)
        elif reminder_type == "weekly":
            next_local = next_local + timedelta(weeks=1)
        elif reminder_type == "monthly":
            next_local = add_months(next_local, 1)
        else:
            raise ValueError("Unsupported reminder_type")

    return next_local.astimezone(timezone.utc)


def add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)
