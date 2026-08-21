# Reminder Service — Status

> Last reviewed: 2026-06-01.
> Документ описывает **текущее** состояние проекта на VDS (systemd, актуальный код, поведение воркеров). Канонический обзор — в `PROJECT.md`, канонические сценарии — в `/root/core-orchestrator/SCENARIOS.md`.
> Полный roadmap / backlog / known issues собраны в `ROADMAP.md` (см. также `/root/server-docs/docs/roadmap.md` для system-level).

## Текущее состояние (snapshot)

### Сервисы (systemd, VDS)

- `reminder-worker.service` — **active (running)**. Цикл `run_loop` опрашивает due-reminders и core-уведомления (включая BLOCKED) каждые `WORKER_POLL_SECONDS` (дефолт 5 сек).
- `reminder-bot.service` — на 2026-06-01 в авто-рестарте, exit-code=1. Причина в `journalctl`: `aiogram.exceptions.TelegramNetworkError: Request timeout error` при `bot.get_me()` (не код, а сетевая проблема к `api.telegram.org`). Бот недоступен, но воркер уведомлений работает.
- `jira-worker.service` — на 2026-06-01 в авто-рестарте, exit-code=0. Jira-интеграция **deprecated** (см. `PROJECT.md`), отказ ожидаем.

### Patch D / Patch E (актуально в коде)

- Patch D (work plan UI в `/task`): read-only отображение latest `work_plan` snapshot (draft/approved/rejected-replan), статусы `work_items`, current `in_progress` item; для `NEEDS_USER_READ` — CTA `/run` и `/ask`. Scan последних 30 append-only snapshots (`CoreTasksRepository.get_recent_work_plan_details(limit=30)`), не full history.
- Patch E (human NEEDS_REVIEW UI): CTA в `/task`, `/needs_review`, push-notify; `/ask` pre-check для `kind=question` (отдельно подсказывает `/run`); explicit «закрыть задачу» / «на доработку» wording.

### Fridge / Meal UI (в коде, в PROJECT.md)

- Команды `/fridge`, `/fridge_add`, `/fridge_remove`, `/fridge_update`, `/meal` живут в `app/bot/handlers.py`.
- Пишут в `events` с `request.domain="fridge"`, `request.fridge_action={...}`, `request.auto_run=True`.
- `/fridge_update` и `/meal` — `request.kind="question"` (LLM-парсинг в core); остальные — `request.kind="task"`.
- См. `PROJECT.md` (раздел "Fridge / Meal") для формата аргументов.

## Текущее состояние (общее)

- Бот и воркер работают на VDS (systemd). `reminder-worker` стабильно держится; `reminder-bot` сейчас падает на сетевых таймаутах к Telegram API.
- Jira в коде присутствует, но для текущей системы считается **deprecated** (см. `PROJECT.md`). По умолчанию `jira-worker` не запускаем.
- Репозиторий на GitHub: `nigorevich9-pixel/reminder-bot`
- `users/reminders/jira_*` в `reminder_db` используются как базовые таблицы; core-оркестратор расширяет БД новыми таблицами (не ломая бота)
- `reminder-bot` также пишет входящие команды/запросы в shared inbox таблицу `events` (для `core-orchestrator`).
- `reminder-worker` также доставляет уведомления по core-задачам (delivery trace в `task_details(kind=tg_delivery)` с retry/backoff):
  - `DONE` → финальный итог пользователю (вопрос+ответ / отчёт) (delivery не меняет `tasks.status`)
  - `FAILED` → ошибка пользователю (delivery не меняет `tasks.status`)
  - `BLOCKED` → нет доступной локальной модели (role/reason из `block_reason`); CTA `/run`
  - `WAITING_USER` → уточняющий вопрос пользователю
  - `NEEDS_REVIEW` → "нужен человек" (для question и task)
  - `STOPPED_BY_USER` → уведомление об остановке
  - `codegen_result` → уведомление (PR URL + статус тестов)

Примечания по совместимости с machine review в core:
- Для финального сообщения бот отправляет пользователю **writer-ответ** и игнорирует `llm_result` от ревьюеров (`purpose=question_review`, `purpose=review_loop`).
- При `WAITING_USER` бот берёт вопрос из `llm_result.clarify_question`, а если его нет — из `waiting_user_reason.question` (это важно для review clarify).

## Подключения

- Postgres URL: `postgresql+asyncpg://reminder_user:reminder_pass@localhost:5432/reminder_db` (env: `DATABASE_URL`)
- Redis URL: `redis://localhost:6379/0` (env: `REDIS_URL`; фактическое использование проверить)
- Env файл: `/root/reminder-bot/.env.systemd`

## Сервисы (systemd)

- `/etc/systemd/system/reminder-bot.service` — Telegram bot
- `/etc/systemd/system/reminder-worker.service` — reminder + core notification worker
- `/etc/systemd/system/jira-worker.service` — Jira poller (deprecated / optional)

## Проверки / тесты (smoke)

- Локальная проверка репозитория: `./check.sh`
- Сквозная проверка всех репо: `/root/test_all.sh`
- Требование безопасности: `DATABASE_URL` должен указывать на test-БД (например `reminder_db_test`) и host `localhost`/`127.0.0.1` (guard включён в `app/config/settings.py`).
- Functional smoke покрывают (см. `TESTS.md`):
  - запись событий в `events` (включая denormalized поля)
  - доставку `DONE/FAILED/WAITING_USER/NEEDS_REVIEW` через stub-бот и корректные delivery attempts
  - `get_recent_work_plan_details` ordering

## Known issues

- Help-текст `/hold` в `/start` вводит в заблуждение: написано «приостановить (пока логируем)», а в core это **терминальная** остановка (`STOPPED_BY_USER`) с отменой очереди/кодогена (см. `/root/core-orchestrator/EVENTS.md`).
- Схема `events` создаётся "если не существует" — на некоторых окружениях это может конфликтовать с ручными изменениями.
- Нотификатор должен быть устойчивым к отсутствию `chat_id` в raw_input (сейчас best-effort).
- **`reminder-bot.service` сейчас не работает** (сетевые таймауты к Telegram API на 2026-06-01). Пока восстановлено не будет, входящие команды `/core`, `/fridge*`, `/meal` и т.п. не доставляются. Воркер уведомлений (`reminder-worker`) не зависит от бота и продолжает работать.

## Осталось сделать (общие)

- Персистентные таймзоны пользователей (если понадобится)
- Доп. очистка/архивирование старых уведомлений
- Выбор репозитория в `/core`: показывать доступные репо (ACL через `project_members`), и использовать `repo_id` в `tool_request` для `repo.*` инструментов (а `project_id` остаётся опциональной подсказкой/маппингом для codegen).
- Unified request в `/core`: убрать split "Вопрос/Задача" в UI; отправлять один "request", классификацию/маршрут определяет `core-orchestrator` planner/policy.
- Priority / criticality: UX для выставления/отображения важности запроса (или хотя бы отображение policy core в `/task`).
- UX: разделить pause vs stop для `/hold` (pause+resume и отдельный stop/cancel), см. `/root/server-docs/docs/roadmap.md`.
- UX: когда задача в `WAITING_USER` и бот просит ответить командой вида `/ask <task_id> <text>`, следующее сообщение пользователя автоматически трактовать как ответ для `/ask <task_id>` (без ввода `/ask <task_id>`).
- Режим "просмотр задач" (list, filters) для удобства пользователя.
- Rate-limit/anti-spam на создание задач.
- Orchestration-задачи (tasks/events/llm_requests/codegen) считаем зоной ответственности `core-orchestrator`; этот проект держим как UI+reminders (+ нотификации).

## Примечание про `events`

- `events` — shared inbox. В ней включены idempotency индексы (`source+external_id`, `payload_hash`).
- Реализация в миграциях `reminder-bot`:
  - table creation (clean installs): `/root/reminder-bot/alembic/versions/f5c3cd383f5b_denormalize_events_fields.py`
  - idempotency indexes: `/root/reminder-bot/alembic/versions/20260204_0001_events_idempotency_indexes.py`
- `core-orchestrator` читает `events`, создаёт `tasks` и дальше ведёт pipeline через `llm_requests/llm_responses`.
