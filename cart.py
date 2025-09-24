from aiogram import Router, F
from aiogram.types import CallbackQuery
import aiosqlite
from config import DB_PATH
from keyboards import get_main_menu_keyboard
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()

@router.callback_query(F.data == "main_cart")
async def show_cart(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT c.id, p.name, p.price, c.quantity, ct.name as city_name
            FROM cart c
            JOIN products p ON c.product_id = p.id
            JOIN cities ct ON p.city_id = ct.id
            WHERE c.user_id = ?
            ORDER BY c.added_at DESC
        """, (callback.from_user.id,))
        cart_items = await cursor.fetchall()

    if not cart_items:
        kb = InlineKeyboardBuilder()
        kb.button(text="🛒 Замовити товар", callback_data="main_order")
        kb.button(text="🔙 Назад", callback_data="back_to_main")
        kb.adjust(1)

        await callback.message.edit_text(
            "🛍️ <b>Ваш кошик порожній</b>\n\nДодайте товари!",
            reply_markup=kb.as_markup()
        )
        await callback.answer()
        return

    total_price = sum(item[2] * item[3] for item in cart_items)
    city_name = cart_items[0][4]
    cart_text = f"🛍️ <b>Ваш кошик ({city_name}):</b>\n\n"

    for _, name, price, quantity, _ in cart_items:
        cart_text += f"📦 <b>{name}</b>\n"
        cart_text += f"💵 {price} грн × {quantity} = {price * quantity} грн\n\n"

    cart_text += f"💰 <b>Всього: {total_price} грн</b>"

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Оформити замовлення", callback_data="cart_checkout")
    kb.button(text="🗑️ Очистити кошик", callback_data="cart_clear")
    kb.button(text="🔙 Назад", callback_data="back_to_main")
    kb.adjust(1)

    await callback.message.edit_text(cart_text, reply_markup=kb.as_markup())
    await callback.answer()