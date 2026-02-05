import argparse
import asyncio
import os

from aiogram import Bot
from dotenv import load_dotenv


def _env_int(name: str) -> int | None:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def _send(*, token: str, chat_id: int, text: str) -> None:
    bot = Bot(token=token)
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    finally:
        await bot.session.close()


def main() -> int:
    load_dotenv()

    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True, help="Alert text")
    ap.add_argument("--unit", default=None, help="systemd unit name (optional)")
    args = ap.parse_args()

    token = (os.getenv("TG_TOKEN") or "").strip()
    chat_id = _env_int("OPS_CHAT_ID")
    if not token:
        raise RuntimeError("TG_TOKEN is not set")
    if chat_id is None:
        raise RuntimeError("OPS_CHAT_ID is not set")

    unit = (args.unit or "").strip()
    text = args.text.strip()
    msg = f"[ALERT] {unit}\n{text}" if unit else f"[ALERT]\n{text}"

    asyncio.run(_send(token=token, chat_id=chat_id, text=msg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

