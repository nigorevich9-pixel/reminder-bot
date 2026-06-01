# reminder-bot — Roadmap / Backlog

> Last reviewed: 2026-06-01.
> Этот файл — **проектный** roadmap для `reminder-bot`: что осталось доделать, что в работе, идеи и риски.
> Каноничный **system-level** roadmap (порядок релизов по всей экосистеме) живёт в `/root/server-docs/docs/roadmap.md`.
> Где искать остальное:
> - "Как работает сейчас": `/root/reminder-bot/STATUS.md` (канонический статус)
> - Сценарии и user-facing команды: `/root/reminder-bot/PROJECT.md`
> - Ops / runbook: `/root/reminder-bot/OPS.md`
> - Env-карта: `/root/reminder-bot/CONFIG.md`
> - Security baseline: `/root/reminder-bot/SECURITY.md`
> - Тесты: `/root/reminder-bot/TESTS.md`

## Известные баги / риски (Known issues)

Источник: `STATUS.md` (раздел "Known issues").

- Help-текст `/hold` в `/start` вводит в заблуждение: написано «приостановить (пока логируем)», а в core это **терминальная** остановка (`STOPPED_BY_USER`) с отменой очереди/кодогена (см. `/root/core-orchestrator/EVENTS.md`).
- Схема `events` создаётся "если не существует" — на некоторых окружениях это может конфликтовать с ручными изменениями схемы.
- Нотификатор должен быть устойчивым к отсутствию `chat_id` в `raw_input` (сейчас best-effort).
- **`reminder-bot.service` сейчас не работает** (сетевые таймауты к Telegram API на 2026-06-01). Пока не восстановлено — входящие команды `/core`, `/fridge*`, `/meal` и т.п. не доставляются. Воркер уведомлений (`reminder-worker`) не зависит от бота и продолжает работать.

## Осталось сделать (общие) — Next steps

Источник: `STATUS.md` (раздел "Осталось сделать (общие)") + `PROJECT.md` (раздел "Planned", "Что есть / чего не хватает").

### UI/UX

- Персистентные таймзоны пользователей (если понадобится).
- Доп. очистка/архивирование старых уведомлений.
- Режим "просмотр задач" (list, filters) для удобства пользователя.
- Rate-limit/anti-spam на создание задач.

### `/core` flow (вопросы/задачи через core)

- Выбор репозитория в `/core`: показывать доступные репо (ACL через `project_members`), использовать `repo_id` в `tool_request` для `repo.*` инструментов (а `project_id` остаётся опциональной подсказкой/маппингом для codegen).
- Unified request в `/core`: убрать split "Вопрос/Задача" в UI; отправлять один "request", классификацию/маршрут определяет `core-orchestrator` planner/policy. **Owner:** reminder-bot (UI) + core-orchestrator (planner).
- Priority / criticality: UX для выставления/отображения важности запроса (или хотя бы отображение policy core в `/task`).
- UX: разделить pause vs stop для `/hold` (pause+resume и отдельный stop/cancel), см. `/root/server-docs/docs/roadmap.md` Improvements backlog #3.
- UX: когда задача в `WAITING_USER` и бот просит ответить командой вида `/ask <task_id> <text>`, следующее сообщение пользователя автоматически трактовать как ответ для `/ask <task_id>` (без ввода `/ask <task_id>`).
- Явная команда "approve" (сейчас её роль выполняет `/run`).

### Fridge / Meal

- Fridge-домен не имеет выделенного UX для редактирования/удаления (только add/remove/inventory/update). Добавить edit/delete (через `/fridge_edit`, `/fridge_delete`) и явный "list by expiry".

### Codegen / Review

- Уведомления о `codegen_result` уже включены в `reminder-worker` (через `process_core_codegen_notifications()`) — отметка, что закрыто.
- Привязка задач к репозиторию в `tool_request` — см. core `STATUS.md` Missing.

## Out of scope (напоминание для контекста)

Источник: `STATUS.md` (раздел "Текущее состояние (общее)") + `PROJECT.md` (раздел "Jira (deprecated)").

- **Jira-интеграция deprecated**: код, миграции и воркер для Jira (`/jira_*`, `jira-worker`) в репо есть, но в рамках текущего roadmap системы Jira **не используется** и не является частью сквозных сценариев оркестратора. По умолчанию `jira-worker` не запускаем. Команды (`/jira`, `/jira_test`, `/jira_watch`, `/jira_unwatch`, `/jira_list`, `/jira_check`) оставлены в коде, но **не должны появляться в актуальном roadmap**. Если захочется вернуть — вынести в отдельный файл, чтобы не путать с активными планами.
- Orchestration-задачи (tasks/events/llm_requests/codegen) считаем зоной ответственности `core-orchestrator`; этот проект держим как UI+reminders (+ нотификации).

## Backlog / идеи (не приоритизировано)

Свободный список мыслей, которые пока не стали формальными задачами.

- Документировать, какие "delivery-категории" (`DONE/FAILED/WAITING_USER/NEEDS_REVIEW/STOPPED_BY_USER/codegen_result`) сейчас активны и какие best-effort vs hard-retry. Частично в `STATUS.md` ("Текущее состояние (общее)"), но не в одном месте.
- Расширить `CONFIG.md` секцией "feature flags" (даже если сейчас нет — место под будущее).
- Изучить: можно ли разделить "reminder delivery" и "core notification" воркеры (сейчас общий `reminder-worker`, цикл 5 сек, опрашивает due-reminders + 6 типов core-уведомлений).
- Добавить в `OPS.md` процедуру "cold-start reminders-bot" (когда сервис лежит и надо понять, сетевая это проблема или код).

## Следующий практический шаг

1. **Починить `reminder-bot.service` (сетевые таймауты к Telegram API)** — пока не работает, входящие команды не доставляются. Скорее всего конфиг `proxy`/`MTProxy` или firewall; сначала диагностика, потом фикс. Без этого `/core`, `/fridge*`, `/meal` фактически мертвы для пользователя.
2. Поправить help-текст `/hold` (или окончательно перейти на split pause/stop) — пользователь может случайно убить задачу.
3. После починки бота — вернуться к UX-плану (unified request, project selection, priority).
