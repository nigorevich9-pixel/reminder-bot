# Reminder Bot — Project Overview

## Назначение
Telegram-бот для напоминаний и уведомлений (с поддержкой Jira intake через polling). Проект — первый шаг к оркестратору, где Telegram используется как command center.

## Основные возможности
- Напоминания: разовые, ежедневные, еженедельные, ежемесячные, cron
- FSM сценарии создания напоминаний с кнопками
- Worker для отправки уведомлений
- Jira polling и подписки на проекты/задачи

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

## Основные команды бота
- `/start` — справка
- `/list`, `/list7`, `/list14`, `/list30` — список напоминаний
- `/new` — создать напоминание
- `/cancel` — отменить создание
- `/jira` — справка по Jira
- `/jira_watch`, `/jira_unwatch`, `/jira_list`, `/jira_test` — Jira подписки

## Окна работы Jira polling
- Активно: 09:00–19:00 (локальное время)
- В 09:00 выполняется catch-up за 19:00→09:00

## Репозиторий
- GitHub: `nigorevich9-pixel/reminder-bot`
