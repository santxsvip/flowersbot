from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from config import MANAGER_CHAT_ID
from states import UserFeedbackState
from keyboards import get_main_menu_keyboard
from aiogram.enums import ParseMode

router = Router()

@router.callback_query(F.data == "main_feedback")
async def main_feedback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserFeedbackState.waiting_for_feedback)
    await callback.message.edit_text(
        "💬 <b>Відправити відгук</b>\n\nНапишіть свій відгук."
    )
    await callback.answer()

@router.message(UserFeedbackState.waiting_for_feedback, F.text)
async def receive_user_feedback(message: Message, state: FSMContext):
    feedback_text = message.text.strip()
    user = message.from_user

    feedback_message = (
        f"💬 <b>НОВИЙ ВІДГУК</b>\n\n"
        f"👤 {user.full_name}\n"
        f"🆔 <a href='tg://user?id={user.id}'>{user.id}</a>\n"
        f"💬 {feedback_text}"
    )

    await message.bot.send_message(MANAGER_CHAT_ID, feedback_message, parse_mode=ParseMode.HTML)
    await message.answer("✅ Дякуємо за відгук!", reply_markup=await get_main_menu_keyboard())
    await state.clear()