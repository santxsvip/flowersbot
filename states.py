from aiogram.fsm.state import State, StatesGroup

class UserFeedbackState(StatesGroup):
    waiting_for_feedback = State()