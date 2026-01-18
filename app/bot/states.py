from aiogram.fsm.state import State, StatesGroup


class NewReminderStates(StatesGroup):
    title = State()
    reminder_type = State()
    day_choice = State()
    date_value = State()
    time_value = State()
    cron_expr = State()


class EditReminderStates(StatesGroup):
    reminder_id = State()
    title = State()
    reminder_type = State()
    day_choice = State()
    date_value = State()
    time_value = State()
    cron_expr = State()


class DeleteReminderStates(StatesGroup):
    reminder_id = State()
