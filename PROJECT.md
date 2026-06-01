# Reminder Bot — Project Overview

## Назначение
`reminder-bot` — Telegram-бот, который выполняет три роли:

- **Напоминания**: хранит и доставляет персональные уведомления по расписанию.
- **UI для оркестратора**: принимает от пользователя вопросы/задачи, пишет их в `events` (shared inbox) и показывает статусы/результаты задач из `core-orchestrator`.
- **UI для домена `fridge`**: команды `/fridge*` и `/meal` — inventory холодильника и рекомендации блюд. Использует `core-orchestrator` как backend (тоже через `events`).

Идея: Telegram — это **command center**, а «умная» часть (оркестрация, state machine, LLM-очередь, codegen, fridge, meal) находится в `core-orchestrator`.

Важно: в коде есть Jira-интеграция, но в рамках текущей системы она считается **deprecated** (см. раздел «Jira»).

## Основные возможности
- Напоминания:
  - разовые, ежедневные, еженедельные, ежемесячные
  - cron-расписания
  - создание/редактирование через FSM (шаги с клавиатурами)
- Доставка уведомлений по расписанию (`reminder-worker`)
- UI для `core-orchestrator`:
  - `/core` — создать «вопрос» или «задачу» для оркестратора (FSM: kind → text → run_mode)
  - `/tasks`, `/task <id>` — посмотреть статус/ответ
  - `/run <id>`, `/hold <id>`, `/ask <id> <text>` — команды в core через `events`
  - transition-driven уведомления по статусам core-задач (`WAITING_USER/NEEDS_REVIEW/DONE/FAILED/STOPPED_BY_USER`) с retry/backoff и delivery trace (`task_details(kind=tg_delivery)`)
- UI для домена `fridge` (через `core-orchestrator`):
  - `/fridge [--expired]` — инвентаризация холодильника
  - `/fridge_add` — добавить продукты (структурированные строки: `name qty unit [status=…] [expires=…] [purchased=…] [kcal_per_100g=…]`)
  - `/fridge_remove` — убрать продукты
  - `/fridge_update` — обновить инвентарь по свободному тексту (LLM-парсинг в core)
  - `/meal <breakfast|lunch|dinner|day|week> [kcal=N] [want=…] [avoid=…]` — рекомендация блюда (LLM)
  - Все fridge/meal-запросы пишутся в `events` с `request.domain="fridge"` и `request.fridge_action={...}` (тип действия + параметры); `request.auto_run=True` (не ждёт ручного `/run`)

## Стек
- Python 3.10, aiogram (Telegram bot framework)
- PostgreSQL (asyncpg + SQLAlchemy)
- Redis (URL в `settings.REDIS_URL`, фактическое использование в коде проверить отдельно)
- Alembic migrations
- systemd services: `reminder-bot.service`, `reminder-worker.service`, `jira-worker.service` (deprecated)

## База данных (ownership)

`reminder-bot` использует общий Postgres `reminder_db` и **владеет** (создаёт/мигрирует) своими таблицами.

### Таблицы, за которые отвечает `reminder-bot`

- `users` — Telegram users (`tg_id`, username, first_name, created_at, …)
- `reminders` — напоминания (one-shot/cron; run_at/cron_expr/timezone/next_run_at/status/…)
- `jira_subscriptions`, `jira_last_seen` — Jira (deprecated, но таблицы/миграции исторически существуют)
- `events` — shared inbox для `core-orchestrator` (бот пишет туда события как UI)

`events` implementation references:
- table creation (clean installs): `/root/reminder-bot/alembic/versions/f5c3cd383f5b_denormalize_events_fields.py`
- idempotency indexes: `/root/reminder-bot/alembic/versions/20260204_0001_events_idempotency_indexes.py`

### Таблицы, которые `reminder-bot` использует, но не мигрирует

- `tasks`, `task_details`, `task_transitions`, `llm_requests`, `llm_responses`, `codegen_jobs`, `projects/*` — зона ответственности `core-orchestrator` (бот читает/показывает статус и отправляет уведомления).

## Архитектура

```
app/
├── bot/
│   ├── main.py                # entrypoint (aiogram Dispatcher + polling)
│   ├── handlers.py            # все Telegram-хэндлеры (команды + FSM)
│   ├── jira_handlers.py       # Jira-команды (подключается опционально, см. HAS_JIRA в main.py)
│   ├── middlewares.py         # DBSessionMiddleware (инжектит AsyncSession в хэндлеры)
│   └── states.py              # FSM-состояния (Reminder FSMs, CoreRequest FSM)
├── config/
│   └── settings.py            # все env-конфиги (см. CONFIG.md)
├── db.py                      # AsyncSessionLocal
├── models.py
├── ops_alert.py               # CLI: python -m app.ops_alert --text '...' [--unit svc]
├── repositories/
│   ├── core_tasks_repository.py   # доступ к core-таблицам (events, tasks, task_details, llm_result, codegen_job)
│   ├── reminder_repository.py
│   ├── user_repository.py
│   └── jira_repository.py         # deprecated
├── services/
│   ├── reminder_service.py
│   ├── user_service.py
│   └── jira_service.py             # deprecated
├── utils/
│   ├── work_plan_display.py       # рендер work_plan в /task
│   ├── human_review_display.py    # CTA для NEEDS_REVIEW
│   ├── datetime.py
│   └── time.py
└── worker/
    ├── runner.py                  # основной loop: due-reminders + 6 типов core-уведомлений
    ├── core_task_notify_worker.py # process_core_{waiting_user,needs_review,done,failed,stopped,codegen}_notifications
    ├── jira_worker.py             # deprecated / off по умолчанию
    └── tasks.py
```

## Как `reminder-bot` работает в системе

### Граница ответственности (самое важное)
- Бот **не делает** оркестрацию задач: не хранит state machine, не формирует промпты, не ходит в LLM и не создаёт PR.
- Бот делает **UI + запись событий + доставку уведомлений**:
  - пишет входящие запросы/команды пользователя в таблицу `events` (Postgres)
  - читает `tasks/task_details/codegen_jobs` и показывает пользователю статус/результат
  - для core-задач, перешедших в финальные статусы, отправляет уведомления (delivery не меняет `tasks.status`)

Канонические сценарии по связке компонентов описаны в:
- `/root/core-orchestrator/SCENARIOS.md`
- `/root/core-orchestrator/EVENTS.md` (контракт `events`)

### Shared inbox: таблица `events`
При `/core`, `/fridge*`, `/meal` и при командах `/run`/`/hold`/`/ask` бот пишет запись в `events` с:
- `source="telegram"`
- `external_id="<chat_id>:<message_id>"` (идемпотентность; для auto-run internal events: `"auto-run:<event_id>"`)
- `payload_hash=sha256(canonical_json(payload))`
- `payload` (jsonb) + денормализованные колонки (`event_type`, `tg_id`, `chat_id`, `request_kind`)

`request_kind` denormalize (см. `app/repositories/core_tasks_repository.py:insert_event`):
- для `event_type="user_request"`: берётся `payload.request.kind` (если None — fallback на `payload.request.fridge_action.type` для fridge-домена)
- для `event_type="user_command"`: берётся `payload.command.name` (например, `run` / `hold` / `ask`)

Формат `payload` см. `/root/core-orchestrator/EVENTS.md`. Важно про текущую реализацию:
- `/core` создаёт только `request.kind in {"question","task"}` (вариант `reminder` в core-контракте зарезервирован; напоминания создаются через `/new` и отдельные таблицы).
- `/fridge`, `/fridge_add`, `/fridge_remove` создают `request.kind="task"`, `request.domain="fridge"`, `request.fridge_action={...}`.
- `/fridge_update` и `/meal` создают `request.kind="question"`, `request.domain="fridge"`, `request.fridge_action={...}` (LLM-driven в core).
- Все fridge/meal-запросы пишут `request.auto_run=True` (не ждут ручного `/run`).
- Команды `/run`/`/hold`/`/ask` пишутся как `event_type="user_command"`.
- Polling `_poll_task_id_and_notify()` после `/core` ищет `task_id` через `task_details(kind=raw_input).content.event_id` (см. `core_tasks_repository.get_task_id_by_event_id`).

Planned: `/core` будет отправлять unified «request» (сырой запрос пользователя + контекст), а классификацию/маршрут (question/task/command/...) будет делать `core-orchestrator` planner/policy.

## Основные команды бота
- `/start` — справка
- `/cancel` — отменить создание напоминания (FSM)

### Напоминания
- `/list` — все уведомления
- `/list7` — уведомления на 7 дней
- `/list14` — уведомления на 14 дней
- `/list30` — уведомления на 30 дней
- `/new` — создать уведомление
- `/edit` — редактировать уведомление (через FSM)
- `/disable <id>` — отключить (пометить done)
- `/delete <id>` — удалить

### Orchestrator UI (core-orchestrator)
- `/core` — создать «вопрос» или «задачу» для оркестратора (FSM: kind → text → run_mode)
- `/tasks` — список твоих задач (последние 20)
- `/task <id>` — статус задачи + work plan (draft/approved, work_items, current step) + последний ответ LLM + (если есть) codegen/PR; для `NEEDS_USER_READ` — CTA `/run` / `/ask`; для `NEEDS_REVIEW` — CTA human approve (`/run`) / reject (`/ask`)
- `/run <task_id>` — запустить задачу/вопрос (approval gate)
- `/hold <task_id>` — остановить/отменить (core переведёт задачу в `STOPPED_BY_USER` и отменит очередь/кодоген)
- `/ask <task_id> <text>` — ответ пользователем на уточняющий вопрос (если задача в `WAITING_USER`, core продолжит диалог и создаст новый `llm_request`); для `NEEDS_REVIEW` + `kind=question` пишет отдельное сообщение «одобрить и закрыть: `/run`»
- `/needs_review` — список задач `NEEDS_REVIEW` + «возраст» в этом статусе

### Fridge / Meal (через core-orchestrator, `domain="fridge"`)
- `/fridge [--expired]` — инвентаризация холодильника; флаг `--expired` показывает просроченные позиции
- `/fridge_add <name...> <qty> <unit> [status=normal|frozen|thawed] [expires=YYYY-MM-DD] [purchased=YYYY-MM-DD] [kcal_per_100g=N]` — добавить продукты
  - Можно несколько строк: `/fridge_add\ngreen apple 1 piece expires=2026-03-20 kcal_per_100g=52\nmilk 1 l`
  - Единицы: g/ml/piece (также можно: l→ml, kg→g, jar/pack/portion→piece)
- `/fridge_remove <name...> <qty> <unit>` — списать продукты (аналогичный формат)
- `/fridge_update` — обновить инвентарь по свободному тексту (LLM-парсится в core, `kind=question`)
- `/meal <breakfast|lunch|dinner|day|week> [kcal=N] [want=…] [avoid=…]` — рекомендация блюда (LLM, `kind=question`)

## Основные сценарии

### 1) Напоминание: создание и доставка
1) Пользователь запускает `/new` и проходит FSM (название → тип → дата/время или cron).
2) Бот пишет напоминание в таблицы `reminders` и т.п.
3) `reminder-worker` периодически проверяет «due reminders» и отправляет сообщения в Telegram.

Важно: напоминания не являются источником `tasks`. Напоминания и задачи/вопросы — разные сущности и разные процессы.

### 2) Вопрос/задача в оркестратор (`/core`)
1) `/core` → выбор: «Вопрос» или «Задача».
2) Ввод текста.
3) Выбор режима:
   - «Запустить сразу» — бот дождётся `task_id` (polling 0.5–5 сек до 120 сек) и автоматически отправит `run`.
   - «Ждать /run» — ничего не отправляется в LLM, пока пользователь не сделает `/run <task_id>`.
4) Бот пишет `events.user_request` (`request.kind=question|task`, без `domain`/`fridge_action`).
5) `core-event-worker` читает `events`, создаёт `tasks` и переводит в `WAITING_APPROVAL`.
6) Бот фоном находит `task_id` по `event_id` (через `task_details(kind=raw_input).content.event_id`) и присылает пользователю сообщение с `/task` и `/run`.

Planned:
- убрать шаг «выбор: Вопрос/Задача»: `/core` создаёт один «запрос», а core классифицирует intent и выбирает сценарий (question/task/command/...) и политику (priority/criticality, web verification, модель/лимиты).

### 3) Fridge/Meal: действие в оркестратор
1) Пользователь запускает `/fridge*` или `/meal`.
2) Бот пишет `events.user_request` с `request.domain="fridge"`, `request.fridge_action={...}`, `request.auto_run=True` (для `/fridge_update` и `/meal` — `request.kind="question"`, для остальных — `"task"`).
3) Дальше — стандартный pipeline core: `core-event-worker` → `tasks` → `llm_requests` → ...
4) Результат (inventory / apply / recommendation) приходит пользователю в TG через `reminder-worker` в финальных статусах (`DONE/FAILED/...`).

### 4) Доставка результата «вопроса» (core → Telegram)
- Когда core переводит задачу в `DONE`, воркер `reminder-worker` отправляет пользователю сообщение вида «Вопрос/Ответ».
  - Delivery **не меняет** `tasks.status`: outcome (`DONE/FAILED/...`) отделён от доставки.
  - Для надёжности доставка пишет attempts в `task_details(kind=tg_delivery)` и делает retry/backoff при временных ошибках (конфиг: `TG_DELIVERY_MAX_ATTEMPTS`, `TG_DELIVERY_MAX_RETRY_WINDOW_SECONDS`).
  - Важно: бот берёт **writer-ответ**, а не результаты ревьюеров. Он игнорирует `task_details(kind=llm_result)` с `purpose in ('question_review','review_loop')` и берёт последний `llm_result` где `purpose` пустой/NULL или один из `json_retry`, `question_rework`, `question_review_limit` (см. `_llm_purpose_filter_sql` в `core_tasks_repository`).
- Когда core переводит задачу в `WAITING_USER`, воркер отправляет one-shot сообщение «Нужно уточнение» и подсказывает `/ask <task_id> ...`.
  - Если в `llm_result` нет `clarify_question` (например, clarify пришёл из machine review), бот берёт вопрос из `task_details(kind=waiting_user_reason).content.question`.
- Идемпотентность уведомлений: `WAITING_USER` помечается через `task_details(kind=tg_waiting_user_notified)` (one-shot).
- `NEEDS_REVIEW` шлёт push-уведомление с CTA «одобрить (`/run`) / на доработку (`/ask`)».

## Что есть / чего не хватает (относительно roadmap core)
- **Есть**: approval gate через `/run` (+ опционально auto-run), запись `events`, просмотр `tasks`/`task_details`, delivery-уведомления `WAITING_USER/NEEDS_REVIEW/DONE/FAILED/STOPPED_BY_USER` с delivery trace + retry/backoff; fridge/meal UI через `domain="fridge"`.
- **Не хватает (актуально сейчас)**:
  - Явной команды «approve» (по сути её роль сейчас выполняет `/run`).
  - `/core` не поддерживает `request.kind=reminder` (и не должен: reminders и tasks/questions — разные сущности; reminders живут отдельно и не создают `tasks`).
  - Уведомления о `codegen_result` включены в `reminder-worker` (через `process_core_codegen_notifications()`).
  - Fridge-домен не имеет выделенного UX для редактирования/удаления (только add/remove/inventory/update).

## Jira (deprecated)
В репозитории есть код, миграции и воркер для Jira (`/jira_*`, `jira-worker`), но в рамках текущего roadmap системы Jira **не используется** и не является частью сквозных сценариев оркестратора.

Команды (в `app/bot/jira_handlers.py`): `/jira`, `/jira_test`, `/jira_watch`, `/jira_unwatch`, `/jira_list`, `/jira_check`.

Рекомендация: считать Jira-интеграцию выключенной по умолчанию (не задавать `JIRA_EMAIL/JIRA_API_TOKEN`, не запускать `jira-worker.service`).

## Репозиторий
- GitHub: `nigorevich9-pixel/reminder-bot`
