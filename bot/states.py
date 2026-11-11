"""aiogram FSM state groups."""
from aiogram.fsm.state import State, StatesGroup


class CreateAccount(StatesGroup):
    waiting_name = State()
    waiting_currency = State()
    waiting_initial_balance = State()
    waiting_confirm = State()


class AddTransaction(StatesGroup):
    waiting_amount = State()
    waiting_category = State()
    waiting_note = State()
    waiting_confirm = State()


class SetBalance(StatesGroup):
    waiting_amount = State()
