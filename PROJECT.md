# Reminder Bot — Project Overview

## Назначение
`reminder-bot` — Telegram-бот, который выполняет две роли:

- **Напоминания**: хранит и доставляет персональные уведомления по расписанию.
- **UI для оркестратора**: принимает от пользователя вопросы/задачи, пишет их в `events` (shared inbox) и показывает статусы/результаты задач из `core-orchestrator`.

Идея: Telegram — это **command center**, а “умная” часть (оркестрация, state machine, LLM очередь, codegen) находится в `core-orchestrator`.

Важно: в коде есть Jira-интеграция, но в рамках текущей системы она считается **deprecated** (см. раздел “Jira”).

## Основные возможности
- Напоминания:
  - разовые, ежедневные, еженедельные, ежемесячные
  - cron-расписания
  - создание/редактирование через FSM (шаги с клавиатурами)
- Доставка уведомлений по расписанию (`reminder-worker`)
- UI для `core-orchestrator`:
  - `/core` — создать “вопрос” или “задачу” для оркестратора
  - `/tasks`, `/task <id>` — посмотреть статус/ответ
  - `/run <id>`, `/hold <id>`, `/ask <id> <text>` — команды в core через `events`
  - авто-доставка ответа пользователю для `SEND_TO_USER`
  - one-shot “нужно уточнение” для `WAITING_USER`

## Стек
- Python, aiogram
- PostgreSQL, Redis
- Alembic migrations
- systemd services

## Архитектура
- `app/bot/*` — Telegram handlers
- `app/services/*` — бизнес-логика
- `app/repositories/*` — доступ к БД
- `app/worker/*` — фоновые воркеры

## Как `reminder-bot` работает в системе

### Граница ответственности (самое важное)
- Бот **не делает** оркестрацию задач: не хранит state machine, не формирует промпты, не ходит в LLM и не создаёт PR.
- Бот делает **UI + запись событий**:
  - пишет входящие запросы/команды пользователя в таблицу `events` (Postgres)
  - читает `tasks/task_details/codegen_jobs` и показывает пользователю статус/результат

Канонические сценарии по связке компонентов описаны в:
- `/root/core-orchestrator/docs/scenarios.md`
- `/root/core-orchestrator/docs/events.md` (контракт `events`)

### Shared inbox: таблица `events`
При `/core` и при командах `/run`/`/hold`/`/ask` бот пишет запись в `events` с:
- `source="telegram"`
- `external_id="<chat_id>:<message_id>"` (идемпотентность)
- `payload_hash=sha256(canonical_json(payload))`
- `payload` (jsonb) + денормализованные колонки (`event_type`, `tg_id`, `chat_id`, `request_kind`)

Формат `payload` см. `/root/core-orchestrator/docs/events.md`. Важно про текущую реализацию:
- `/core` создаёт только `request.kind in {"question","task"}` (вариант `reminder` в core-контракте зарезервирован; напоминания создаются через `/new` и отдельные таблицы).
- Команды `/run`/`/hold`/`/ask` пишутся как `event_type="user_command"`.

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
- `/core` — создать “вопрос” или “задачу” для оркестратора
- `/tasks` — список твоих задач (последние 20)
- `/task <id>` — статус задачи + последний ответ LLM + (если есть) состояние codegen/PR
- `/run <task_id>` — запустить задачу/вопрос (approval gate)
- `/hold <task_id>` — “приостановить” (core переведёт задачу в `STOPPED_BY_USER` и отменит очередь/кодоген)
- `/ask <task_id> <text>` — ответ пользователем на уточняющий вопрос (если задача в `WAITING_USER`, core продолжит диалог и создаст новый `llm_request`)
- `/needs_review` — список задач `NEEDS_REVIEW` + “возраст” в этом статусе

## Основные сценарии

### 1) Напоминание: создание и доставка
1) Пользователь запускает `/new` и проходит FSM (название → тип → дата/время или cron).
2) Бот пишет напоминание в таблицы `reminders` и т.п.
3) `reminder-worker` периодически проверяет “due reminders” и отправляет сообщения в Telegram.

Важно: напоминания не являются источником `tasks`. Напоминания и задачи/вопросы — разные сущности и разные процессы.

### 2) Вопрос/задача в оркестратор (`/core`)
1) `/core` → выбор: “Вопрос” или “Задача”.
2) Ввод текста.
3) Выбор режима:
   - “Запустить сразу” — бот дождётся `task_id` и автоматически отправит `run`.
   - “Ждать /run” — ничего не отправляется в LLM, пока пользователь не сделает `/run <task_id>`.
4) Бот пишет `events.user_request`.
5) `core-event-worker` читает `events`, создаёт `tasks` и переводит в `WAITING_APPROVAL`.
6) Бот фоном (polling) находит `task_id` по `event_id` и присылает пользователю сообщение с `/task` и `/run`.

### 3) Доставка результата “вопроса” (core → Telegram)
- Когда core переводит задачу в `SEND_TO_USER`, воркер `reminder-worker` отправляет пользователю сообщение вида “Вопрос/Ответ” и переводит задачу в `DONE`.
  - Важно: бот берёт **writer-ответ**, а не результаты ревьюеров. Он игнорирует `task_details(kind=llm_result)` с `purpose in ('question_review','review_loop')` и берёт последний `llm_result` где `purpose` пустой/NULL или один из `json_retry`, `question_rework`, `question_review_limit`.
- Когда core переводит задачу в `WAITING_USER`, воркер отправляет one-shot сообщение “Нужно уточнение” и подсказывает `/ask <task_id> ...`.
  - Если в `llm_result` нет `clarify_question` (например, clarify пришёл из machine review), бот берёт вопрос из `task_details(kind=waiting_user_reason).content.question`.

## Что есть / чего не хватает (относительно roadmap core)
- **Есть**: approval gate через `/run` (+ опционально auto-run), запись `events`, просмотр `tasks`/`task_details`, авто-доставка `SEND_TO_USER`, one-shot уведомление `WAITING_USER`.
- **Не хватает (актуально сейчас)**:
  - Явной команды “approve” (по сути её роль сейчас выполняет `/run`).
  - `/core` не поддерживает `request.kind=reminder` (и не должен: reminders и tasks/questions — разные сущности; reminders живут отдельно и не создают `tasks`).
  - Уведомления о `codegen_result` включены в `reminder-worker` (через `process_core_codegen_notifications()`).

## Jira (deprecated)
В репозитории есть код, миграции и воркер для Jira (`/jira_*`, `jira-worker`), но в рамках текущего roadmap системы Jira **не используется** и не является частью сквозных сценариев оркестратора.
Рекомендация: считать Jira-интеграцию выключенной по умолчанию (не задавать `JIRA_EMAIL/JIRA_API_TOKEN`, не запускать `jira-worker.service`).

## Репозиторий
- GitHub: `nigorevich9-pixel/reminder-bot`
