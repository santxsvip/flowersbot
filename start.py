from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart

from ..database import register_user
from keyboards import get_main_menu_keyboard

router = Router()

@router.message(CommandStart())
async def start_cmd(message: Message):
    user = message.from_user
    await register_user(user.id, user.username, user.first_name, user.last_name)

    await message.answer(
        "🌸 Ласкаво просимо!\nОберіть дію:",
        reply_markup=await get_main_menu_keyboard()
    )

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text(
        "🌸 Оберіть дію:",
        reply_markup=await get_main_menu_keyboard()
    )
    await callback.answer()