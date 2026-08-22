# reminder-bot — Roadmap / Backlog

> Last reviewed: 2026-08-22.
> Telegram UI + reminders + fridge. **Очередь экосистемы:** [`/root/server-docs/docs/roadmap.md`](/root/server-docs/docs/roadmap.md).
> Harness: [`/root/core-orchestrator/ROADMAP.md`](/root/core-orchestrator/ROADMAP.md). Снимок: [`STATUS.md`](STATUS.md). Сценарии команд: [`PROJECT.md`](PROJECT.md).

Этот репо **не** владеет codegen loop. Единственный пункт, который бьёт по **P0** harness: без живого бота нет Telegram E2E. Остальной UX — Later относительно replace pipeline.

---

## Карта фич (этот репо)

| ID | Фича | Приоритет | Статус | Что решает |
|---|---|---|---|---|
| WRK | `reminder-worker` (reminders + core notify) | — | prod-used | DONE/FAILED/NEEDS_REVIEW/codegen_result в TG |
| D | Patch D: план в `/task` | — | код | Человек видит work items |
| E | Patch E CTA `/run` `/ask` | — | код | Human gate |
| FR | Fridge/meal команды | — | код | Бытовой трек, не harness |
| **BOT** | `reminder-bot.service` жив | **Ops / блокер Telegram P0** | **лежит** (TG timeouts с 2026-06-01) | `/core` с телефона |
| HOLD | Честный текст `/hold` = stop | Ops [S] | баг в help | Не убить задачу «на паузу» |
| UNIF | Unified request (без Вопрос/Задача) | Later | нет | Нужен planner в **core** |
| REPO | Выбор репо в `/core` | Later | нет | Нужен ACL/`project_members` |
| PAUS | Pause vs stop | Later | нет | Сейчас hold = terminal |
| ASK | Следующее сообщение = ответ на `/ask` | Later | нет | UX WAITING_USER |
| APPR | Отдельная команда approve | Later | нет | Сейчас роль `/run` |
| LST | Список задач / фильтры | Later | нет | Удобство |
| TZ | Персистентные таймзоны | Later | нет | Если понадобится |
| FR2 | Fridge edit/delete, list by expiry | Later (продукт) | нет | Не P0 |
| PMUX | Permission-modes UX | после core Later PMOD | нет | UI не опережает сервер |
| CHK | Отображение markdown-check results | после core P1.3 | нет | Нужны данные от core |
| SKL | `/add_skill` | после core P2.2 | нет | Сначала SKILL.md в core |

Jira — **deprecated**, не в очереди.

---

## Порядок (этот репо)

```text
Ops: починить reminder-bot.service     ← нужно для Telegram-ветки core P0
Ops: поправить help /hold
        │
        ▼
(ждать core P0 / P1.3 / P2.x)
        │
        ▼
Later UX: unified request, repo picker, pause/resume
Later продукт: fridge edit/delete
```

Не делать permission-modes / skills UI «вперёд» сервера.

### Ops — бот должен отвечать

**Решает:** входящие `/core`, `/fridge*`, `/meal`. Воркер уведомлений от этого не зависит.

Пока бот мёртв, core P0 всё ещё можно гонять **минуя Telegram** (прямые events / ops), но заявленный пользовательский E2E — нет.

### Ops [S] — `/hold`

В core это `STOPPED_BY_USER`, не пауза. Либо поменять help, либо когда-нибудь Later сделать pause+resume в core.

---

## Out of scope

- Оркестрация tasks/llm/codegen — **core**.
- Jira-команды в актуальной очереди не держать.

---

## Later (не над Ops)

- Delivery-категории в одном месте (частично STATUS).
- Feature flags в CONFIG.md.
- Разделить reminder delivery и core notify workers.
- Cold-start процедура в OPS.md.
- Rate-limit, архив уведомлений, явный approve.

---

## Следующий практический шаг

1. **Починить `reminder-bot.service`** (прокси/firewall к `api.telegram.org`) — иначе нет Telegram P0.
2. Help-текст `/hold`.
3. UX-план (unified request, project picker) — **после** core P0, не вместо.
