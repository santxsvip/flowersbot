from aiogram import Router, F
from aiogram.types import CallbackQuery
import aiosqlite
from config import DB_PATH
from database import get_user_cart_city
from keyboards import get_main_menu_keyboard
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()

@router.callback_query(F.data == "main_order")
async def main_order(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT name FROM cities")
        cities = [row[0] for row in await cursor.fetchall()]

    if not cities:
        cities = ["Київ", "Дніпро", "Львів"]

    user_cart_city = await get_user_cart_city(callback.from_user.id)

    kb = InlineKeyboardBuilder()
    for city in cities:
        if user_cart_city and user_cart_city[1] != city:
            kb.button(text=f"🚫 {city} (очистіть кошик)", callback_data="cart_city_conflict")
        else:
            kb.button(text=city, callback_data=f"city:{city}")
    kb.button(text="🔙 Назад", callback_data="back_to_main")
    kb.adjust(2)

    cart_warning = ""
    if user_cart_city:
        cart_warning = f"\n\n⚠️ У кошику вже є товари з міста {user_cart_city[1]}."

    await callback.message.edit_text(
        f"🏙️ Оберіть своє місто:{cart_warning}",
        reply_markup=kb.as_markup()
    )
    await callback.answer()