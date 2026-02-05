## Тесты в `reminder-bot`

Этот репозиторий использует реальные Postgres-таблицы (через общую test-БД) для smoke/functional тестов воркеров.

### Как запускать

- Локально (через общий раннер): `cd /root && ./test_all.sh`
- Только этот репо: `cd /root/reminder-bot && DATABASE_URL=... ./check.sh`

Важно: `DATABASE_URL` должен указывать на `*_test` БД на `localhost`/`127.0.0.1`. Перед тестами `./check.sh` очищает test-БД (reset schema или TRUNCATE fallback) и прогоняет миграции.

### Набор тестов

Файл: `tests/test_core_events_and_notify_worker.py`

#### `test_insert_event_writes_denormalized_columns`

- **Что тестирует**: `CoreTasksRepository.insert_event()` корректно записывает `events.payload` (jsonb) и денормализованные поля `event_type`, `tg_id`, `chat_id`, `request_kind`.
- **Данные**:
  - Вставляется `events` с payload вида:
    - `event_type="user_request"`
    - `tg: {tg_id, chat_id, message_id}`
    - `request: {kind, text, project_id, attachments}`
- **Проверки**:
  - Поля в строке `events` совпадают с ожидаемыми значениями.

#### `test_send_to_user_transitions_to_done_and_sends_message`

- **Что тестирует**: `process_core_task_notifications()` берёт задачу со статусом `SEND_TO_USER`, отправляет сообщение в TG и переводит задачу в `DONE`.
- **Данные**:
  - `users`: upsert по `tg_id=9001`
  - `tasks`: создаётся задача `status='SEND_TO_USER'`
  - `task_details`:
    - `kind='raw_input'`, `content` содержит `tg.chat_id=12345`, `tg.tg_id=9001`, `text="What?"`
    - `kind='llm_result'`, `content` содержит `answer="Because."`, `clarify_question=None`
  - `bot`: stub с `send_message()`, который записывает вызовы в `bot.sent`
- **Проверки**:
  - функция возвращает `sent == 1`
  - `tasks.status` стал `DONE`
  - `bot.sent` содержит ровно 1 сообщение в `chat_id=12345`
  - текст содержит `"Ответ:"`

#### `test_waiting_user_is_notified_once`

- **Что тестирует**: `process_core_waiting_user_notifications()` отправляет пользователю сообщение “нужно уточнение” только один раз (идемпотентность через `task_details.kind='tg_waiting_user_notified'`).
- **Данные**:
  - `users`: upsert по `tg_id=9002`
  - `tasks`: создаётся задача `status='WAITING_USER'`
  - `task_details`:
    - `raw_input` с `tg.chat_id=54321`
    - `llm_result` с `clarify_question="Clarify?"`, `answer=None`
- **Проверки**:
  - первый запуск возвращает `1`, второй `0`
  - в `task_details` ровно одна запись `tg_waiting_user_notified`
  - реально отправлено ровно одно сообщение в `bot.sent`

### Что пока не покрыто (идеи для следующих тестов)

- Ошибки отправки в TG (`send_message` кидает исключение) и повторные попытки/поведение транзакции.
- Кейсы, когда в `raw_input`/`llm_result` нет нужных полей (ожидаемый `FAILED` и reason).
