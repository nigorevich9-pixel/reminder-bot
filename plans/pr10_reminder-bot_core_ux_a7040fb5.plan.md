---
name: Reminder-bot core UX
overview: "Улучшаем UX Telegram-бота для core: показываем task_id после создания события, добавляем выбор “запустить сразу / ждать /run”, и добавляем команду `/tasks` для списка задач пользователя."
todos:
  - id: repo-return-event-id
    content: Сделать `CoreTasksRepository.insert_event()` возвращающим `event_id` через `RETURNING id` + добавить метод `get_task_id_by_event_id()`.
    status: completed
  - id: bot-core-choice-flow
    content: "Расширить FSM (`CoreRequestStates.run_mode`) и изменить `/core` flow: после текста спросить 2 варианта, затем вставить event и стартануть background notify."
    status: completed
  - id: background-notify-and-auto-run
    content: Реализовать фоновый polling task_id по event_id и отправку сообщения; при выборе “запустить сразу” — автоматически создать `user_command(run)` event.
    status: completed
  - id: tasks-command
    content: Добавить команду `/tasks` (список задач пользователя) + обновить help в `/start`.
    status: completed
isProject: false
repo: reminder-bot
pr_number: 10
pr_url: https://github.com/nigorevich9-pixel/reminder-bot/pull/10
matched_by: time_window,title_similarity
match_confidence: medium
source_plan_path: /root/.cursor/plans/reminder-bot_core_ux_a7040fb5.plan.md
source_mtime: 2026-02-04T10:59:46Z
---

## Что меняем

- В `reminder-bot` после создания `user_request` события бот должен **фоном дождаться** создания `tasks` и прислать отдельное сообщение с **task_id**.
- После ввода текста (в FSM `CoreRequestStates.text`) бот должен **спросить выбор**:
  - **Запустить сразу**: после появления `task_id` бот сам создаёт `user_command(run)` событие (аналог `/run <id>`).
  - **Ждать /run**: только присылаем `task_id` и подсказки.
- Добавляем команду `**/tasks**` (как алиасов не делаем — по твоему выбору), которая выводит последние задачи текущего TG пользователя.

## Где в коде

- Telegram handlers: `[/root/reminder-bot/app/bot/handlers.py](/root/reminder-bot/app/bot/handlers.py)`
  - Сейчас создание события происходит тут:

```246:279:/root/reminder-bot/app/bot/handlers.py
@router.message(CoreRequestStates.text)
async def core_text_handler(message: Message, state: FSMContext, session: AsyncSession):
    ...
    external_id = f"{message.chat.id}:{message.message_id}"
    await repo.insert_event(source="telegram", external_id=external_id, payload=payload)
    await session.commit()
    await state.clear()
    await message.answer("Принято. Создал событие в core. Дальше жди task в статусе WAITING_APPROVAL.")
```

- Репозиторий core-таблиц: `[/root/reminder-bot/app/repositories/core_tasks_repository.py](/root/reminder-bot/app/repositories/core_tasks_repository.py)`
  - Сейчас `insert_event()` ничего не возвращает, поэтому `event_id` не доступен:

```41:63:/root/reminder-bot/app/repositories/core_tasks_repository.py
async def insert_event(self, *, source: str, external_id: str, payload: dict) -> None:
    ...
    await self._session.execute(
        sa.text(
            "INSERT INTO events (source, external_id, payload_hash, payload, event_type, tg_id, chat_id, request_kind) "
            "VALUES (:source, :external_id, :payload_hash, CAST(:payload AS jsonb), :event_type, :tg_id, :chat_id, :request_kind)"
        ),
        {...},
    )
```

- Sessionmaker для фоновых задач: `[/root/reminder-bot/app/db.py](/root/reminder-bot/app/db.py)` (`AsyncSessionLocal`).

## Реализация (логика)

- **FSM расширение**: добавить `CoreRequestStates.run_mode` в `[/root/reminder-bot/app/bot/states.py](/root/reminder-bot/app/bot/states.py)`.
- **Двухшаговый flow** в handlers:
  - `core_text_handler` сохраняет текст/метаданные в state и показывает клавиатуру с 2 вариантами.
  - Новый handler на `CoreRequestStates.run_mode`:
    - вставляет `events(user_request)` и получает `event_id` (см. ниже)
    - отвечает “Принято…”
    - запускает `asyncio.create_task(...)` с background notify.
- **Получение event_id**:
  - изменить `CoreTasksRepository.insert_event()` так, чтобы делал `... RETURNING id` и возвращал `event_id: int`.
- **Поиск task_id по event_id** (polling в фоне):
  - добавить в `CoreTasksRepository` метод `get_task_id_by_event_id(event_id)` через `task_details(kind='raw_input')`:
    - `SELECT task_id FROM task_details WHERE kind='raw_input' AND CAST(content->>'event_id' AS int)=:event_id ORDER BY id DESC LIMIT 1`
  - фоновой джобой опрашивать до фиксированного дедлайна (например, 120s) с backoff.
  - как только нашли `task_id` — отправить отдельное сообщение в чат.
- **Auto-run**:
  - если выбран “запустить сразу”, фоновой джобой после нахождения `task_id` создать `events(user_command, command.name='run')` (то же, что `_insert_core_command` делает для `/run`). Для `external_id` использовать уникальную строку вроде `auto-run:<event_id>`.
- `**/tasks**`:
  - добавить handler `@router.message(Command("tasks"))`.
  - добавить метод репозитория `list_tasks_for_tg(tg_id, limit)` (join `tasks` + `users` по `tg_id`).
  - формат: список строк `#<id> • <status> • <title>` (например, последние 20) + подсказка `/task <id>`.
- **Обновить `/start` help**: добавить `/tasks`.

## Проверка (ручная)

- `/core` → “Вопрос” → текст → выбрать “ждать /run”: бот присылает “Принято…”, затем отдельным сообщением `task #ID создан…`.
- `/core` → текст → выбрать “запустить сразу”: бот присылает `task #ID создан…` и затем подтверждение, что отправил run (или объединённо).
- `/tasks`: показывает список задач именно текущего TG пользователя.

## Ограничения/заметки

- Фоновая джоба должна открывать **новую** DB-сессию через `AsyncSessionLocal` (middleware-сессия закрывается после handler).

