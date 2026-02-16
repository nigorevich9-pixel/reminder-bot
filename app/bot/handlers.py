import asyncio
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states import (
    CoreRequestStates,
    DeleteReminderStates,
    DisableReminderStates,
    EditReminderStates,
    NewReminderStates,
)
from app.config.settings import settings
from app.repositories.reminder_repository import ReminderRepository
from app.repositories.core_tasks_repository import CoreTasksRepository
from app.repositories.user_repository import UserRepository
from app.services.reminder_service import ReminderService
from app.services.user_service import UserService
from app.db import AsyncSessionLocal
from app.utils.datetime import build_user_datetime, format_user_datetime, parse_user_date


router = Router()

TYPE_OPTIONS = {
    "Разово": "one_time",
    "Ежедневно": "daily",
    "Еженедельно": "weekly",
    "Ежемесячно": "monthly",
    "Cron": "cron",
}

DAY_OPTIONS = {
    "Сегодня": 0,
    "Завтра": 1,
    "Другая дата": None,
}

TIME_PRESETS = {
    "Через 1 минуту": timedelta(minutes=1),
    "Через 10 минут": timedelta(minutes=10),
    "Через 1 час": timedelta(hours=1),
}

FIXED_TIME_OPTIONS = {
    "09:00": (9, 0),
    "12:00": (12, 0),
    "18:00": (18, 0),
}


def _plural_days(value: int) -> str:
    if value % 10 == 1 and value % 100 != 11:
        return "день"
    if value % 10 in {2, 3, 4} and value % 100 not in {12, 13, 14}:
        return "дня"
    return "дней"


def _format_month_day(value: date) -> str:
    months = [
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ]
    return f"{value.day:02d} {months[value.month - 1]}"


def _format_reminders(reminders) -> str:
    if not reminders:
        return "Пока нет уведомлений."

    tz_name = settings.default_timezone
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()

    def reminder_dt(reminder):
        return reminder.next_run_at or reminder.run_at

    def sort_key(reminder):
        dt = reminder_dt(reminder)
        sort_dt = dt if dt else datetime.max.replace(tzinfo=UTC)
        status_rank = 0 if reminder.status == "active" else 1
        return (status_rank, sort_dt)

    sorted_items = sorted(reminders, key=sort_key)
    blocks: dict[str, list[str]] = {}

    for reminder in sorted_items:
        dt = reminder_dt(reminder)
        if dt:
            local_dt = dt.astimezone(tz)
            local_date = local_dt.date()
            days_diff = (local_date - today).days
            if days_diff == 0:
                header = "Сегодня"
            elif days_diff == 1:
                header = "Завтра"
            elif 2 <= days_diff <= 7:
                header = f"Через {days_diff} {_plural_days(days_diff)}"
            else:
                header = _format_month_day(local_date)
            time_part = local_dt.strftime("%H:%M")
        else:
            header = "Без даты"
            time_part = "--:--"

        if reminder.status != "active":
            header = f"{header} • выполнено"

        line = f"#{reminder.id} • {time_part} • {reminder.title} • {reminder.reminder_type}"
        blocks.setdefault(header, []).append(line)

    parts = []
    for header, lines in blocks.items():
        parts.append(f"{header}:\n" + "\n".join(lines))
    return "\n\n".join(parts)


def _time_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="09:00"), KeyboardButton(
                text="12:00"), KeyboardButton(text="18:00")],
            [KeyboardButton(text="Через 1 минуту"),
             KeyboardButton(text="Через 10 минут")],
            [KeyboardButton(text="Через 1 час"),
             KeyboardButton(text="Ввести время")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def _get_or_create_user(session: AsyncSession, message: Message):
    repo = UserRepository(session)
    service = UserService(repo)
    return await service.get_or_create(
        tg_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )


@router.message(Command("start"))
async def start_handler(message: Message, session: AsyncSession):
    await _get_or_create_user(session, message)
    await message.answer(
        "Бот напоминаний готов.\n"
        "Команды:\n"
        "/list — все уведомления\n"
        "/list7 — уведомления на 7 дней\n"
        "/list14 — уведомления на 14 дней\n"
        "/list30 — уведомления на 30 дней\n"
        "/new — создать уведомление\n"
        "/edit — редактировать уведомление\n"
        "/disable — отключить уведомление\n"
        "/delete — удалить уведомление\n"
        "/core — вопрос/задача для оркестратора\n"
        "/task <id> — статус задачи\n"
        "/tasks — список твоих задач\n"
        "/run <task_id> — запустить задачу/вопрос\n"
        "/hold <task_id> — приостановить (пока логируем)\n"
        "/ask <task_id> <text> — ответить на уточняющий вопрос LLM\n"
        "/cancel — отменить создание"
    )


@router.message(Command("list"))
async def list_handler(message: Message, session: AsyncSession):
    user = await _get_or_create_user(session, message)
    reminders = await ReminderService(ReminderRepository(session)).list_all(user.id)
    await message.answer(_format_reminders(reminders))


@router.message(Command("list7"))
async def list7_handler(message: Message, session: AsyncSession):
    user = await _get_or_create_user(session, message)
    reminders = await ReminderService(ReminderRepository(session)).list_next_days(user.id, 7)
    await message.answer(_format_reminders(reminders))


@router.message(Command("list14"))
async def list14_handler(message: Message, session: AsyncSession):
    user = await _get_or_create_user(session, message)
    reminders = await ReminderService(ReminderRepository(session)).list_next_days(user.id, 14)
    await message.answer(_format_reminders(reminders))


@router.message(Command("list30"))
async def list30_handler(message: Message, session: AsyncSession):
    user = await _get_or_create_user(session, message)
    reminders = await ReminderService(ReminderRepository(session)).list_next_days(user.id, 30)
    await message.answer(_format_reminders(reminders))


@router.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Создание уведомления отменено.", reply_markup=ReplyKeyboardRemove())


@router.message(Command("tasks"))
async def tasks_list_handler(message: Message, session: AsyncSession):
    await _get_or_create_user(session, message)
    repo = CoreTasksRepository(session)
    tasks = await repo.list_tasks_for_tg(tg_id=message.from_user.id, limit=20)
    if not tasks:
        await message.answer("Пока нет задач. Создай через /core")
        return
    lines = [f"#{t['id']} • {t['status']} • {t['title']}" for t in tasks]
    await message.answer("Твои задачи:\n" + "\n".join(lines) + "\n\nПодробности: /task <id>")


def _format_age(delta_seconds: float) -> str:
    seconds = max(int(delta_seconds), 0)
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24
    if days > 0:
        return f"{days}d {hours % 24}h"
    if hours > 0:
        return f"{hours}h {minutes % 60}m"
    return f"{minutes}m"


@router.message(Command("needs_review"))
async def needs_review_handler(message: Message, session: AsyncSession):
    await _get_or_create_user(session, message)
    repo = CoreTasksRepository(session)
    tasks = await repo.list_needs_review_tasks_for_tg(tg_id=message.from_user.id, limit=50)
    if not tasks:
        await message.answer("NEEDS_REVIEW задач нет.")
        return

    now = datetime.now(UTC)
    lines = ["NEEDS_REVIEW задачи:"]
    for t in tasks:
        task_id = t.get("id")
        title = (t.get("title") or "").strip()
        needs_review_at = t.get("needs_review_at")
        age = None
        if isinstance(needs_review_at, datetime):
            dt = needs_review_at
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            age = _format_age((now - dt).total_seconds())
        age_text = age or "unknown"
        title_text = title.splitlines()[0].strip() if title else ""
        if len(title_text) > 80:
            title_text = title_text[:80] + "…"
        lines.append(f"- #{task_id} • {age_text} • {title_text}")
    lines.append("")
    lines.append("Подробности: /task <id>")
    await message.answer("\n".join(lines))


@router.message(Command("core"))
async def core_handler(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(CoreRequestStates.kind)
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Вопрос"), KeyboardButton(text="Задача")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Что отправляем в оркестратор?", reply_markup=kb)


@router.message(CoreRequestStates.kind)
async def core_kind_handler(message: Message, state: FSMContext):
    kind_text = (message.text or "").strip().lower()
    if kind_text == "вопрос":
        kind = "question"
    elif kind_text == "задача":
        kind = "task"
    else:
        await message.answer("Выбери: Вопрос или Задача")
        return

    await state.update_data(kind=kind)
    await state.set_state(CoreRequestStates.text)
    await message.answer("Отправь текст.", reply_markup=ReplyKeyboardRemove())


@router.message(CoreRequestStates.text)
async def core_text_handler(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    kind = data.get("kind")
    text = (message.text or "").strip()
    if kind not in {"question", "task"}:
        await state.clear()
        await message.answer("Ошибка: неизвестный тип запроса. Повтори /core")
        return
    if not text:
        await message.answer("Текст пустой. Отправь текст.")
        return

    await state.update_data(text=text)
    await state.set_state(CoreRequestStates.run_mode)
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Запустить сразу")],
            [KeyboardButton(text="Ждать /run")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Как поступаем?", reply_markup=kb)


async def _poll_task_id_and_notify(
    *,
    bot,
    chat_id: int,
    tg_id: int,
    event_id: int,
    auto_run: bool,
    timeout_s: float = 120.0,
) -> None:
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(timeout_s, 1.0)
        backoff_s = 0.5
        task_id: int | None = None

        while loop.time() < deadline:
            async with AsyncSessionLocal() as bg_session:
                repo = CoreTasksRepository(bg_session)
                task_id = await repo.get_task_id_by_event_id(event_id=event_id)
            if task_id is not None:
                break
            await asyncio.sleep(backoff_s)
            backoff_s = min(backoff_s * 1.5, 5.0)

        if task_id is None:
            await bot.send_message(
                chat_id,
                "Не дождался создания task_id. Проверь позже через /tasks или /task <id>.",
            )
            return

        await bot.send_message(
            chat_id,
            f"Создана задача: task #{task_id} • статус WAITING_APPROVAL.\n"
            f"Посмотреть: /task {task_id}\n"
            f"Запустить: /run {task_id}",
        )

        if not auto_run:
            return

        async with AsyncSessionLocal() as bg_session:
            repo = CoreTasksRepository(bg_session)
            payload = {
                "event_type": "user_command",
                "tg": {
                    "tg_id": tg_id,
                    "chat_id": chat_id,
                    "message_id": 0,
                },
                "command": {
                    "name": "run",
                    "task_id": task_id,
                    "text": None,
                },
            }
            await repo.insert_event(source="telegram", external_id=f"auto-run:{event_id}", payload=payload)
            await bg_session.commit()

        await bot.send_message(chat_id, f"Ок. Отправил run для task #{task_id}.")
    except Exception as e:
        try:
            await bot.send_message(chat_id, f"Ошибка при ожидании task_id: {e}")
        except Exception:
            pass


@router.message(CoreRequestStates.run_mode)
async def core_run_mode_handler(message: Message, state: FSMContext, session: AsyncSession):
    mode_text = (message.text or "").strip().lower()
    if mode_text in {"запустить сразу", "сразу", "run"}:
        auto_run = True
    elif mode_text in {"ждать /run", "ждать", "wait"}:
        auto_run = False
    else:
        await message.answer("Выбери: Запустить сразу или Ждать /run")
        return

    data = await state.get_data()
    kind = data.get("kind")
    text = data.get("text")
    if kind not in {"question", "task"} or not isinstance(text, str) or not text.strip():
        await state.clear()
        await message.answer("Ошибка: данные запроса потерялись. Повтори /core", reply_markup=ReplyKeyboardRemove())
        return

    await _get_or_create_user(session, message)
    repo = CoreTasksRepository(session)
    payload = {
        "event_type": "user_request",
        "tg": {
            "tg_id": message.from_user.id,
            "chat_id": message.chat.id,
            "message_id": message.message_id,
        },
        "request": {
            "kind": kind,
            "text": text.strip(),
            "project_id": None,
            "attachments": [],
        },
    }
    external_id = f"{message.chat.id}:{message.message_id}"
    event_id = await repo.insert_event(source="telegram", external_id=external_id, payload=payload)
    await session.commit()
    await state.clear()
    await message.answer(
        "Принято. Создал событие в core. Дальше жди task в статусе WAITING_APPROVAL.",
        reply_markup=ReplyKeyboardRemove(),
    )

    asyncio.create_task(
        _poll_task_id_and_notify(
            bot=message.bot,
            chat_id=message.chat.id,
            tg_id=message.from_user.id,
            event_id=event_id,
            auto_run=auto_run,
        )
    )


async def _insert_core_command(
    session: AsyncSession, message: Message, *, name: str, task_id: int, text: str | None
) -> None:
    await _get_or_create_user(session, message)
    repo = CoreTasksRepository(session)
    payload = {
        "event_type": "user_command",
        "tg": {
            "tg_id": message.from_user.id,
            "chat_id": message.chat.id,
            "message_id": message.message_id,
        },
        "command": {
            "name": name,
            "task_id": task_id,
            "text": text,
        },
    }
    external_id = f"{message.chat.id}:{message.message_id}"
    await repo.insert_event(source="telegram", external_id=external_id, payload=payload)


@router.message(Command("run"))
async def run_task_handler(message: Message, session: AsyncSession):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("Использование: /run <task_id>")
        return
    task_id = int(args[1].strip())
    await _insert_core_command(session, message, name="run", task_id=task_id, text=None)
    await session.commit()
    await message.answer(f"Ок. Отправил run для task #{task_id}.")


@router.message(Command("hold"))
async def hold_task_handler(message: Message, session: AsyncSession):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("Использование: /hold <task_id>")
        return
    task_id = int(args[1].strip())
    await _insert_core_command(session, message, name="hold", task_id=task_id, text=None)
    await session.commit()
    await message.answer(f"Ок. Отправил hold для task #{task_id}.")


@router.message(Command("ask"))
async def ask_task_handler(message: Message, session: AsyncSession):
    args = (message.text or "").split(maxsplit=2)
    if len(args) < 3 or not args[1].strip().isdigit() or not args[2].strip():
        await message.answer("Использование: /ask <task_id> <text>")
        return
    task_id = int(args[1].strip())
    text = args[2].strip()
    await _insert_core_command(session, message, name="ask", task_id=task_id, text=text)
    await session.commit()
    await message.answer(f"Ок. Отправил ask для task #{task_id}.")


@router.message(Command("task"))
async def task_status_handler(message: Message, session: AsyncSession):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip().isdigit():
        await message.answer("Использование: /task <id>")
        return
    task_id = int(args[1].strip())
    repo = CoreTasksRepository(session)
    task = await repo.get_task(task_id=task_id)
    if not task:
        await message.answer("Задача не найдена.")
        return
    llm_result = await repo.get_latest_llm_result(task_id=task_id)
    answer = await repo.get_latest_llm_answer(task_id=task_id)
    codegen_job = await repo.get_latest_codegen_job(task_id=task_id)
    msg = f"task #{task['id']} • {task['status']}\n{task['title']}"
    if answer:
        msg += f"\n\nОтвет:\n{answer}"
    elif llm_result and isinstance(llm_result.get("clarify_question"), str) and llm_result.get("clarify_question").strip():
        msg += f"\n\nУточнение:\n{llm_result.get('clarify_question').strip()}"
    elif llm_result and llm_result.get("json_invalid") is True:
        msg += "\n\nОтвет от LLM не в JSON формате — поставил на авто-повтор. Если продолжает ломаться, уйдёт в NEEDS_REVIEW."

    if codegen_job:
        pr_url = (codegen_job.get("pr_url") or "").strip()
        status = (codegen_job.get("status") or "").strip()
        error = (codegen_job.get("error") or "").strip()
        if pr_url:
            msg += f"\n\nPR:\n{pr_url}"
        elif status:
            msg += f"\n\nCodegen:\n{status}"
            if status == "FAILED" and error:
                msg += f"\n{error}"
    await message.answer(msg)


@router.message(Command("new"))
async def new_handler(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(NewReminderStates.title)
    await message.answer("Название уведомления:", reply_markup=ReplyKeyboardRemove())


@router.message(Command("edit"))
async def edit_handler(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(EditReminderStates.reminder_id)
    await message.answer(
        "Введите номер уведомления для редактирования (например, 12):",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(Command("disable"))
async def disable_handler(message: Message, state: FSMContext, session: AsyncSession):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Введите ID уведомления для отключения:")
        await state.set_state(DisableReminderStates.reminder_id)
        return
    if not args[1].strip().isdigit():
        await message.answer("Использование: /disable <id> или отправь id в следующем сообщении")
        return
    reminder_id = int(args[1].strip())
    user = await _get_or_create_user(session, message)
    service = ReminderService(ReminderRepository(session))
    reminder = await service.get_by_id_for_user(reminder_id, user.id)
    if not reminder:
        await message.answer("Уведомление не найдено или не принадлежит тебе.")
        return
    await service.mark_done(reminder)
    await message.answer(f"Уведомление #{reminder.id} отключено (status=done).")


@router.message(Command("delete"))
async def delete_handler(message: Message, state: FSMContext, session: AsyncSession):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        # Ask for ID in next message
        await message.answer("Введите ID уведомления для удаления:")
        await state.set_state(DeleteReminderStates.reminder_id)
        return
    if not args[1].strip().isdigit():
        await message.answer("Использование: /delete <id> или отправь id в следующем сообщении")
        return
    reminder_id = int(args[1].strip())
    user = await _get_or_create_user(session, message)
    service = ReminderService(ReminderRepository(session))
    reminder = await service.get_by_id_for_user(reminder_id, user.id)
    if not reminder:
        await message.answer("Уведомление не найдено или не принадлежит тебе.")
        return
    await service.delete(reminder)
    await message.answer(f"Уведомление #{reminder_id} удалено.")


@router.message(DeleteReminderStates.reminder_id)
async def delete_id_handler(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Нужен числовой ID уведомления.")
        return
    reminder_id = int(raw)
    user = await _get_or_create_user(session, message)
    service = ReminderService(ReminderRepository(session))
    reminder = await service.get_by_id_for_user(reminder_id, user.id)
    if not reminder:
        await message.answer("Уведомление не найдено или не принадлежит тебе.")
        return
    await service.delete(reminder)
    await state.clear()
    await message.answer(f"Уведомление #{reminder_id} удалено.")


@router.message(DisableReminderStates.reminder_id)
async def disable_id_handler(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Нужен числовой ID уведомления.")
        return
    reminder_id = int(raw)
    user = await _get_or_create_user(session, message)
    service = ReminderService(ReminderRepository(session))
    reminder = await service.get_by_id_for_user(reminder_id, user.id)
    if not reminder:
        await message.answer("Уведомление не найдено или не принадлежит тебе.")
        return
    await service.mark_done(reminder)
    await state.clear()
    await message.answer(f"Уведомление #{reminder_id} отключено (status=done).")


@router.message(NewReminderStates.title)
async def new_title_handler(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым.")
        return
    await state.update_data(title=title)
    await state.set_state(NewReminderStates.reminder_type)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Разово"), KeyboardButton(text="Ежедневно")],
            [KeyboardButton(text="Еженедельно"),
             KeyboardButton(text="Ежемесячно")],
            [KeyboardButton(text="Cron")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Тип уведомления:", reply_markup=keyboard)


@router.message(EditReminderStates.reminder_id)
async def edit_id_handler(message: Message, state: FSMContext, session: AsyncSession):
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Нужен числовой ID уведомления.")
        return
    reminder_id = int(raw)
    user = await _get_or_create_user(session, message)
    reminder = await ReminderService(ReminderRepository(session)).get_by_id_for_user(
        reminder_id, user.id
    )
    if not reminder:
        await message.answer("Уведомление не найдено или не принадлежит тебе.")
        return
    await state.update_data(reminder_id=reminder_id)
    await state.set_state(EditReminderStates.title)
    await message.answer(
        f"Новое название (сейчас: {reminder.title}):",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(EditReminderStates.title)
async def edit_title_handler(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым.")
        return
    await state.update_data(title=title)
    await state.set_state(EditReminderStates.reminder_type)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Разово"), KeyboardButton(text="Ежедневно")],
            [KeyboardButton(text="Еженедельно"),
             KeyboardButton(text="Ежемесячно")],
            [KeyboardButton(text="Cron")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Тип уведомления:", reply_markup=keyboard)


@router.message(NewReminderStates.reminder_type)
async def new_type_handler(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    reminder_type = TYPE_OPTIONS.get(raw) or raw.lower()
    if reminder_type not in {"one_time", "daily", "weekly", "monthly", "cron"}:
        await message.answer("Неверный тип. Выбери из кнопок.")
        return
    await state.update_data(reminder_type=reminder_type)
    if reminder_type == "cron":
        await state.set_state(NewReminderStates.cron_expr)
        await message.answer(
            "Cron: минуты → часы → день_месяца → месяц → день_недели.\n"
            "Примеры (ежедневные):\n"
            "• Каждый день в 09:00 — `0 9 * * *`\n"
            "• По будням в 18:30 — `30 18 * * 1-5`\n"
            "• Со вторника по четверг в 10:00 — `0 10 * * 2-4`\n"
            "• Каждые 2 часа — `0 */2 * * *`\n"
            "Примеры (ежемесячные):\n"
            "• 1‑го числа в 09:00 — `0 9 1 * *`\n"
            "• 15‑го числа в 09:00 — `0 9 15 * *`",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await state.set_state(NewReminderStates.day_choice)
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Сегодня"),
                 KeyboardButton(text="Завтра")],
                [KeyboardButton(text="Другая дата")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await message.answer("Когда напомнить?", reply_markup=keyboard)


@router.message(EditReminderStates.reminder_type)
async def edit_type_handler(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    reminder_type = TYPE_OPTIONS.get(raw) or raw.lower()
    if reminder_type not in {"one_time", "daily", "weekly", "monthly", "cron"}:
        await message.answer("Неверный тип. Выбери из кнопок.")
        return
    await state.update_data(reminder_type=reminder_type)
    if reminder_type == "cron":
        await state.set_state(EditReminderStates.cron_expr)
        await message.answer(
            "Cron: минуты → часы → день_месяца → месяц → день_недели.\n"
            "Примеры (ежедневные):\n"
            "• Каждый день в 09:00 — `0 9 * * *`\n"
            "• По будням в 18:30 — `30 18 * * 1-5`\n"
            "• Со вторника по четверг в 10:00 — `0 10 * * 2-4`\n"
            "• Каждые 2 часа — `0 */2 * * *`\n"
            "Примеры (ежемесячные):\n"
            "• 1‑го числа в 09:00 — `0 9 1 * *`\n"
            "• 15‑го числа в 09:00 — `0 9 15 * *`",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await state.set_state(EditReminderStates.day_choice)
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Сегодня"),
                 KeyboardButton(text="Завтра")],
                [KeyboardButton(text="Другая дата")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await message.answer("Когда напомнить?", reply_markup=keyboard)


@router.message(NewReminderStates.day_choice)
async def new_day_choice_handler(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    if raw not in DAY_OPTIONS:
        await message.answer("Выбери из кнопок.")
        return
    offset = DAY_OPTIONS[raw]
    if offset is None:
        await state.set_state(NewReminderStates.date_value)
        await message.answer("Дата (DD-MM-YYYY):", reply_markup=ReplyKeyboardRemove())
        return
    target_date = date.today() + timedelta(days=offset)
    await state.update_data(
        date_value=target_date.strftime("%Y-%m-%d"),
        day_offset=offset,
    )
    await state.set_state(NewReminderStates.time_value)
    await message.answer("Выбери время или введи вручную:", reply_markup=_time_keyboard())


@router.message(EditReminderStates.day_choice)
async def edit_day_choice_handler(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    if raw not in DAY_OPTIONS:
        await message.answer("Выбери из кнопок.")
        return
    offset = DAY_OPTIONS[raw]
    if offset is None:
        await state.set_state(EditReminderStates.date_value)
        await message.answer("Дата (DD-MM-YYYY):", reply_markup=ReplyKeyboardRemove())
        return
    target_date = date.today() + timedelta(days=offset)
    await state.update_data(
        date_value=target_date.strftime("%Y-%m-%d"),
        day_offset=offset,
    )
    await state.set_state(EditReminderStates.time_value)
    await message.answer("Выбери время или введи вручную:", reply_markup=_time_keyboard())


@router.message(NewReminderStates.date_value)
async def new_date_handler(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    try:
        parse_user_date(raw)
    except ValueError:
        await message.answer("Неверный формат. Пример: 20-01-2026 или 20 01 2026")
        return
    await state.update_data(date_value=raw)
    await state.update_data(day_offset=None)
    await state.set_state(NewReminderStates.time_value)
    await message.answer("Выбери время или введи вручную:", reply_markup=_time_keyboard())


@router.message(EditReminderStates.date_value)
async def edit_date_handler(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    try:
        parse_user_date(raw)
    except ValueError:
        await message.answer("Неверный формат. Пример: 20-01-2026 или 20 01 2026")
        return
    await state.update_data(date_value=raw)
    await state.update_data(day_offset=None)
    await state.set_state(EditReminderStates.time_value)
    await message.answer("Выбери время или введи вручную:", reply_markup=_time_keyboard())


@router.message(NewReminderStates.time_value)
async def new_time_handler(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    tz_name = settings.default_timezone
    raw = (message.text or "").strip()
    if raw in DAY_OPTIONS:
        offset = DAY_OPTIONS[raw]
        if offset is None:
            await state.set_state(NewReminderStates.date_value)
            await message.answer("Дата (DD-MM-YYYY):", reply_markup=ReplyKeyboardRemove())
            return
        target_date = date.today() + timedelta(days=offset)
        await state.update_data(date_value=target_date.strftime("%Y-%m-%d"))
        await message.answer("Выбери время или введи вручную:", reply_markup=_time_keyboard())
        return
    if raw == "Ввести время":
        await message.answer("Время (HH:MM) или 'H M':", reply_markup=ReplyKeyboardRemove())
        return
    if raw in TIME_PRESETS:
        tz = ZoneInfo(tz_name)
        base_time = (datetime.now(tz) + TIME_PRESETS[raw]).time()
        date_value = data.get("date_value")
        if not date_value:
            await message.answer("Сначала выбери дату.")
            return
        target_date = parse_user_date(date_value)
        run_local = datetime.combine(target_date, base_time).replace(tzinfo=tz)
        run_at = run_local.astimezone(UTC)
    elif raw in FIXED_TIME_OPTIONS:
        tz = ZoneInfo(tz_name)
        date_value = data.get("date_value")
        if not date_value:
            await message.answer("Сначала выбери дату.")
            return
        target_date = parse_user_date(date_value)
        hour, minute = FIXED_TIME_OPTIONS[raw]
        run_local = datetime.combine(
            target_date, datetime.min.time()).replace(tzinfo=tz)
        run_local = run_local.replace(hour=hour, minute=minute)
        run_at = run_local.astimezone(UTC)
    else:
        try:
            run_at = build_user_datetime(data["date_value"], raw, tz_name)
        except ValueError:
            await message.answer("Неверный формат времени. Пример: 09:30 или 9 30")
            return

    reminder = await ReminderService(ReminderRepository(session)).create(
        user_id=(await _get_or_create_user(session, message)).id,
        title=data["title"],
        message=data["title"],
        reminder_type=data["reminder_type"],
        run_at=run_at,
        cron_expr=None,
        timezone=tz_name,
    )
    await state.clear()
    await message.answer(
        f"Создано уведомление #{reminder.id} на {format_user_datetime(reminder.next_run_at, tz_name)}",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(EditReminderStates.time_value)
async def edit_time_handler(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    tz_name = settings.default_timezone
    raw = (message.text or "").strip()
    if raw in DAY_OPTIONS:
        offset = DAY_OPTIONS[raw]
        if offset is None:
            await state.set_state(EditReminderStates.date_value)
            await message.answer("Дата (DD-MM-YYYY):", reply_markup=ReplyKeyboardRemove())
            return
        target_date = date.today() + timedelta(days=offset)
        await state.update_data(date_value=target_date.strftime("%Y-%m-%d"))
        await message.answer("Выбери время или введи вручную:", reply_markup=_time_keyboard())
        return
    if raw == "Ввести время":
        await message.answer("Время (HH:MM) или 'H M':", reply_markup=ReplyKeyboardRemove())
        return
    if raw in TIME_PRESETS:
        tz = ZoneInfo(tz_name)
        base_time = (datetime.now(tz) + TIME_PRESETS[raw]).time()
        date_value = data.get("date_value")
        if not date_value:
            await message.answer("Сначала выбери дату.")
            return
        target_date = parse_user_date(date_value)
        run_local = datetime.combine(target_date, base_time).replace(tzinfo=tz)
        run_at = run_local.astimezone(UTC)
    elif raw in FIXED_TIME_OPTIONS:
        tz = ZoneInfo(tz_name)
        date_value = data.get("date_value")
        if not date_value:
            await message.answer("Сначала выбери дату.")
            return
        target_date = parse_user_date(date_value)
        hour, minute = FIXED_TIME_OPTIONS[raw]
        run_local = datetime.combine(
            target_date, datetime.min.time()).replace(tzinfo=tz)
        run_local = run_local.replace(hour=hour, minute=minute)
        run_at = run_local.astimezone(UTC)
    else:
        try:
            run_at = build_user_datetime(data["date_value"], raw, tz_name)
        except ValueError:
            await message.answer("Неверный формат времени. Пример: 09:30 или 9 30")
            return

    user = await _get_or_create_user(session, message)
    reminder = await ReminderService(ReminderRepository(session)).get_by_id_for_user(
        data["reminder_id"], user.id
    )
    if not reminder:
        await state.clear()
        await message.answer("Уведомление не найдено или не принадлежит тебе.")
        return

    reminder = await ReminderService(ReminderRepository(session)).update(
        reminder=reminder,
        title=data["title"],
        message=data["title"],
        reminder_type=data["reminder_type"],
        run_at=run_at,
        cron_expr=None,
        timezone=tz_name,
    )
    await state.clear()
    await message.answer(
        f"Обновлено уведомление #{reminder.id} на {format_user_datetime(reminder.next_run_at, tz_name)}",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(NewReminderStates.cron_expr)
async def new_cron_handler(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    tz_name = settings.default_timezone
    cron_expr = (message.text or "").strip()
    if not cron_expr:
        await message.answer("Cron выражение не может быть пустым.")
        return
    try:
        reminder = await ReminderService(ReminderRepository(session)).create(
            user_id=(await _get_or_create_user(session, message)).id,
            title=data["title"],
            message=data["title"],
            reminder_type="cron",
            run_at=None,
            cron_expr=cron_expr,
            timezone=tz_name,
        )
    except Exception:
        await message.answer("Не удалось разобрать cron. Пример: 0 9 * * *")
        return
    await state.clear()
    await message.answer(
        f"Создано уведомление #{reminder.id} на {format_user_datetime(reminder.next_run_at, tz_name)}"
    )


@router.message(EditReminderStates.cron_expr)
async def edit_cron_handler(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    tz_name = settings.default_timezone
    cron_expr = (message.text or "").strip()
    if not cron_expr:
        await message.answer("Cron выражение не может быть пустым.")
        return
    try:
        user = await _get_or_create_user(session, message)
        reminder = await ReminderService(ReminderRepository(session)).get_by_id_for_user(
            data["reminder_id"], user.id
        )
        if not reminder:
            await state.clear()
            await message.answer("Уведомление не найдено или не принадлежит тебе.")
            return
        reminder = await ReminderService(ReminderRepository(session)).update(
            reminder=reminder,
            title=data["title"],
            message=data["title"],
            reminder_type="cron",
            run_at=None,
            cron_expr=cron_expr,
            timezone=tz_name,
        )
    except Exception:
        await message.answer("Не удалось разобрать cron. Пример: 0 9 * * *")
        return
    await state.clear()
    await message.answer(
        f"Обновлено уведомление #{reminder.id} на {format_user_datetime(reminder.next_run_at, tz_name)}"
    )
