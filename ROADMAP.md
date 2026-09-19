# reminder-bot — Roadmap / Backlog

> Last reviewed: 2026-09-19 (docs / cross-repo alignment — **not** a live systemd re-probe).
> Telegram UI + reminders + fridge. **Очередь экосистемы:** [server-docs/docs/roadmap.md](https://github.com/nigorevich9-pixel/server-docs/blob/main/docs/roadmap.md).
> Harness / docs/core: [core-orchestrator/ROADMAP.md](https://github.com/nigorevich9-pixel/core-orchestrator/blob/main/ROADMAP.md). Снимок: [`STATUS.md`](STATUS.md). Сценарии команд: [`PROJECT.md`](PROJECT.md).

Этот репо **не** владеет codegen loop и **не** является prerequisite для harness **P0** replace E2E. Живой Telegram-бот — блокер только для **Telegram / end-user E2E**. Core P0 replace E2E идёт через Core Control / direct events. Остальной UX — Later относительно native core path.

---

## Карта фич (этот репо)

| ID | Фича | Приоритет | Статус | Что решает |
|---|---|---|---|---|
| WRK | `reminder-worker` (reminders + core notify) | — | prod-used | DONE/FAILED/NEEDS_REVIEW/codegen_result в TG |
| D | Patch D: план в `/task` | — | код | Человек видит work items |
| E | Patch E CTA `/run` `/ask` | — | код | Human gate |
| FR | Fridge/meal команды | — | код | Бытовой трек, не harness |
| CHK | Display markdown-check results из `task_details` | cheap UI consumer (не ждать весь core P1.3) | **код** | Читает `review_checks_summary` / `review_check_result`; секция пустая, если контракта/данных нет |
| **BOT** | `reminder-bot.service` жив | **Ops / блокер только Telegram E2E** (не core P0) | last verified down **2026-06-01**; **current live state needs ops recheck** | `/core` с телефона |
| HOLD | Help `/hold` = «остановить окончательно» | Ops **[S]** safety bug | баг в help | Сейчас hold = terminal `STOPPED_BY_USER`, не pause |
| INBOX | Thin HITL: Working / Needs Action / Done-Unread | Later | нет | Core [#106](https://github.com/nigorevich9-pixel/core-orchestrator/issues/106) operator inbox projection **merged**; Telegram — тонкая поверхность (status, CTA, summaries, links). [task-tracker-web](https://github.com/nigorevich9-pixel/task-tracker-web) endpoint — отдельный in-progress slice. Не интеграция Pizza/Orca/Polide. |
| UNIF | Unified request (без Вопрос/Задача) | Later | нет | Нужен planner в **core** |
| REPO | Выбор репо в `/core` (Telegram picker) | Later (UI) | нет | Core Control web уже принимает явный `repo_id`; Telegram picker **не** реализован |
| PAUS | Pause vs stop | Later | нет | Сейчас hold = terminal |
| ASK | Следующее сообщение = ответ на `/ask` | Later | нет | UX WAITING_USER |
| APPR | Отдельная команда approve | Later | нет | Сейчас роль `/run` |
| LST | Список задач / фильтры | Later | нет | Удобство |
| TZ | Персистентные таймзоны | Later | нет | Если понадобится |
| FR2 | Fridge edit/delete, list by expiry | Later (продукт) | нет | Не P0 |
| PMUX | Permission-modes UX | после core Later PMOD | нет | UI не опережает сервер |
| SKL | `/add_skill` | после core P2.2 | нет | Сначала SKILL.md в core |

Jira — **deprecated**, не в очереди.

---

## Порядок (этот репо vs docs/core)

Системный порядок (**docs/core**): **P0** → **P0.1** parallel transport → **P0.2** baseline → **P0.3** decision gates → remaining native **P1**.

```text
Ops [S]: help /hold = «остановить окончательно»
Ops: recheck / restore reminder-bot.service
        ← блокер только Telegram / end-user E2E
        ← не prerequisite для core P0 replace E2E
        │
        ▼
docs/core: P0 → P0.1 parallel transport → P0.2 baseline
           → P0.3 decision gates → remaining native P1
  (replace E2E already via Core Control / direct events)
        │
        ▼
Later UX: thin HITL (Working / Needs Action / Done-Unread),
          unified request, Telegram repo picker, pause/resume
Later продукт: fridge edit/delete
```

Не делать permission-modes / skills UI «вперёд» сервера. Не строить в Telegram IDE / task-board (богатый desktop UX — не здесь).

### Ops — бот должен отвечать (Telegram E2E)

**Решает:** входящие `/core`, `/fridge*`, `/meal`. Воркер уведомлений от этого не зависит.

Last verified down **2026-06-01** (`TelegramNetworkError` / timeouts к `api.telegram.org`). **Current live state needs ops recheck** — этот docs-review не зондировал systemd.

Пока бот недоступен, **core P0 replace E2E уже можно и нужно гонять минуя Telegram** (Core Control / direct events). Живой бот **не** harness-P0 prerequisite. Заявленный пользовательский Telegram E2E — да, блокер.

### Ops [S] — `/hold` (safety bug)

В `/start` help сейчас: «приостановить (пока логируем)». В core это **терминальная** остановка `STOPPED_BY_USER` (очередь/кодоген отменяются), не пауза. Пока pause/resume — Later, текст обязан прямо говорить **«остановить окончательно»**.

---

## Out of scope

- Оркестрация tasks/llm/codegen — **core**.
- Operator inbox projection — core [#106](https://github.com/nigorevich9-pixel/core-orchestrator/issues/106) (merged); HTTP surface — task-tracker-web (отдельный slice).
- Jira-команды в актуальной очереди не держать.
- Pizza Bot / Orca / Polide — источники идей для Later UX, **не** заявленные интеграции.

---

## Later (не над Ops, не над core P0)

- Pizza-like Action/Unread notification model: три внешних состояния (**Working** / **Needs Action** / **Done-Unread**). Будить человека только если нужен выбор, задача упала без recovery, или есть готовый результат. Внутренние `RUNNING / NEEDS_LLM_REVIEW / PUSHED / …` — в core/task details, в TG только по запросу.
- Durable approval: checkpoint живёт в core; бот лишь показывает. CTA: approve / reject / (позже) edit proposed action, если тип операции допускает.
- Тонкая mobile surface: status, Needs Action, краткий diff/result summary, approve/reject, ссылка на PR/preview/logs. Preview/deploy results — surfacing URL + tests/build/deploy status + короткий failure summary, когда sandbox/deploy adapter появится в core.
- Telegram repo picker (`repo_id`) — UI здесь; явный `repo_id` в Core Control web уже есть и **не** означает, что picker в боте сделан.
- Delivery-категории в одном месте (частично STATUS).
- Feature flags в CONFIG.md.
- Разделить reminder delivery и core notify workers.
- Cold-start процедура в OPS.md.
- Rate-limit, архив уведомлений, явный approve.

---

## Следующий практический шаг

1. **Ops recheck `reminder-bot.service`** (last verified down 2026-06-01). Если всё ещё down — починить прокси/firewall к `api.telegram.org`. Это нужно для **Telegram / end-user E2E**, не для core P0.
2. Safety [S]: help-текст `/hold` → «остановить окончательно».
3. Later UX (thin HITL, unified request, Telegram repo picker) — **после** docs/core P0, не вместо.
