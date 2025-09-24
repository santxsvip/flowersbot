from aiogram.utils.keyboard import InlineKeyboardBuilder

async def get_main_menu_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Замовити товар", callback_data="main_order")
    kb.button(text="🛍️ Кошик", callback_data="main_cart")
    kb.button(text="💬 Відгук", callback_data="main_feedback")
    kb.adjust(1)
    return kb.as_markup()