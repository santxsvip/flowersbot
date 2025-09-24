import asyncio
import aiosqlite
import re
import logging
import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
MANAGER_CHAT_ID = -1002989893222
ADMIN_IDS = [6982991715, 7682254485]

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable not set. Please set it to your Telegram bot token.")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

DB_PATH = "flowers.db"

# -------------------------------
# FSM States
# -------------------------------
class AddCity(StatesGroup):
    waiting_for_name = State()
    waiting_for_products = State()

class EditCity(StatesGroup):
    waiting_for_new_name = State()

class AddProduct(StatesGroup):
    cities = State()
    photo = State()
    name = State()
    description = State()
    price = State()

class EditProduct(StatesGroup):
    waiting_for_field = State()
    waiting_for_value = State()

class DeleteProduct(StatesGroup):
    waiting_for_cities = State()

class OrderStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_area = State()
    waiting_for_comment = State()

class FeedbackStates(StatesGroup):
    waiting_for_accept_message = State()
    waiting_for_reject_reason = State()

class UserFeedbackState(StatesGroup):
    waiting_for_feedback = State()

class PDFTermsState(StatesGroup):
    waiting_for_content = State()

class CartQuantityState(StatesGroup):
    waiting_for_quantity = State()

# -------------------------------
# Database Initialization
# -------------------------------
async def init_db():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS cities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE
            )
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city_id INTEGER,
                name TEXT,
                description TEXT,
                price REAL,
                photo TEXT,
                FOREIGN KEY(city_id) REFERENCES cities(id)
            )
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_id INTEGER,
                phone TEXT,
                area TEXT,
                comment TEXT,
                paid INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                agreed_to_terms INTEGER DEFAULT 0,
                registered_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS cart (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_id INTEGER,
                quantity INTEGER DEFAULT 1,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(product_id) REFERENCES products(id)
            )
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS terms_content (
                id INTEGER PRIMARY KEY,
                content TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            await db.commit()
            logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise

# -------------------------------
# Helper Functions
# -------------------------------
def valid_phone(phone: str) -> bool:
    return bool(re.fullmatch(r'(\+380\d{9}|0\d{9})', phone))

async def safe_send_message(chat_id: int, text: str, reply_markup=None, parse_mode=None):
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
        logger.info(f"Message sent successfully to {chat_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to send message to {chat_id}: {e}")
        return False

async def register_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT OR IGNORE INTO users (id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            """, (user_id, username, first_name, last_name))
            await db.commit()
    except Exception as e:
        logger.error(f"Error registering user: {e}")

async def check_user_terms_agreement(user_id: int) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT agreed_to_terms FROM users WHERE id=?", (user_id,))
            row = await cursor.fetchone()
            return row and row[0] == 1
    except Exception as e:
        logger.error(f"Error checking terms agreement: {e}")
        return False

async def get_user_cart_city(user_id: int):
    """Get the city of products in user's cart"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT DISTINCT c.id, c.name
                FROM cart ca
                JOIN products p ON ca.product_id = p.id
                JOIN cities c ON p.city_id = c.id
                WHERE ca.user_id = ?
                LIMIT 1
            """, (user_id,))
            result = await cursor.fetchone()
            return result if result else None
    except Exception as e:
        logger.error(f"Error getting user cart city: {e}")
        return None

def create_terms_pdf(content: str) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    
    # Title
    c.setFont("Helvetica-Bold", 16)
    try:
        c.drawString(100, 750, "УМОВИ ВИКОРИСТАННЯ МАГАЗИНУ")
    except:
        c.drawString(100, 750, "TERMS OF USE")
    
    # Date
    c.setFont("Helvetica", 10)
    date_str = datetime.now().strftime("%d.%m.%Y")
    try:
        c.drawString(100, 720, f"Дата створення: {date_str}")
    except:
        c.drawString(100, 720, f"Created: {date_str}")
    
    # Content - handle Ukrainian characters
    c.setFont("Helvetica", 12)
    lines = content.split('\n')
    y_position = 680
    
    for line in lines:
        if y_position < 50:
            c.showPage()
            c.setFont("Helvetica", 12)
            y_position = 750
        
        # Handle long lines
        if len(line) > 70:
            words = line.split(' ')
            current_line = ""
            for word in words:
                if len(current_line + word) < 70:
                    current_line += word + " "
                else:
                    try:
                        c.drawString(100, y_position, current_line.strip())
                    except:
                        # Fallback for non-ASCII characters
                        safe_line = current_line.strip().encode('utf-8', errors='replace').decode('utf-8')
                        c.drawString(100, y_position, safe_line)
                    y_position -= 20
                    current_line = word + " "
            if current_line:
                try:
                    c.drawString(100, y_position, current_line.strip())
                except:
                    safe_line = current_line.strip().encode('utf-8', errors='replace').decode('utf-8')
                    c.drawString(100, y_position, safe_line)
                y_position -= 20
        else:
            try:
                c.drawString(100, y_position, line)
            except:
                safe_line = line.encode('utf-8', errors='replace').decode('utf-8')
                c.drawString(100, y_position, safe_line)
            y_position -= 20
    
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

async def get_main_menu_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🛒 Замовити товар", callback_data="main_order")
    kb.button(text="🛍️ Кошик", callback_data="main_cart")
    kb.button(text="💬 Відправити відгук", callback_data="main_feedback")
    kb.adjust(1)
    return kb.as_markup()

# -------------------------------
# Start Command and Terms
# -------------------------------
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    await register_user(user.id, user.username, user.first_name, user.last_name)
    
    if await check_user_terms_agreement(user.id):
        await message.answer(
            "🌸 Ласкаво просимо назад!\nОберіть дію:",
            reply_markup=await get_main_menu_keyboard()
        )
        return
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT content FROM terms_content ORDER BY created_at DESC LIMIT 1")
            row = await cursor.fetchone()
        
        if not row:
            default_terms = """УМОВИ ВИКОРИСТАННЯ МАГАЗИНУ КВІТІВ

1. ЗАГАЛЬНІ ПОЛОЖЕННЯ
Використовуючи наші послуги, ви погоджуєтесь з цими умовами.

2. ЗАМОВЛЕННЯ ТА ОПЛАТА
- Замовлення приймаються через Telegram-бот
- Оплата здійснюється при отриманні
- Мінімальна сума замовлення - 200 грн

3. ДОСТАВКА
- Доставка здійснюється протягом 1-3 днів
- Вартість доставки розраховується індивідуально

4. ПОВЕРНЕННЯ ТА ОБМІН
- Свіжі квіти поверненню не підлягають
- У разі браку товару - повний возврат коштів

5. КОНФІДЕНЦІЙНІСТЬ
- Ваші персональні дані захищені
- Інформація не передається третім особам

6. КОНТАКТИ
Telegram: @flower_shop_support"""
            terms_content = default_terms
        else:
            terms_content = row[0]
        
        pdf_bytes = create_terms_pdf(terms_content)
        pdf_file = BufferedInputFile(pdf_bytes, filename="terms_and_conditions.pdf")
        
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Приймаю умови", callback_data="terms_accept")
        kb.button(text="❌ Не приймаю", callback_data="terms_decline")
        kb.adjust(1)
        
        await message.answer_document(
            pdf_file,
            caption="📋 <b>Умови використання магазину</b>\n\n"
                   "Будь ласка, ознайомтеся з умовами використання нашого магазину. "
                   "Для продовження роботи з ботом необхідно прийняти умови.",
            reply_markup=kb.as_markup()
        )
        
    except Exception as e:
        logger.error(f"Error in cmd_start: {e}")
        await message.answer("❌ Виникла помилка. Спробуйте пізніше.")

@dp.callback_query(F.data == "terms_accept")
async def accept_terms(callback: CallbackQuery):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET agreed_to_terms=1 WHERE id=?", (callback.from_user.id,))
            await db.commit()
        
        await callback.message.answer(
            "✅ <b>Дякуємо!</b>\n\n"
            "Ви прийняли умови використання. Тепер ви можете користуватися всіма функціями магазину.\n\n"
            "Оберіть дію:",
            reply_markup=await get_main_menu_keyboard()
        )
        await callback.answer("Умови прийнято ✅")
    except Exception as e:
        logger.error(f"Error accepting terms: {e}")
        await callback.answer("❌ Помилка")

@dp.callback_query(F.data == "terms_decline")
async def decline_terms(callback: CallbackQuery):
    await callback.message.answer(
        "❌ <b>Умови не прийнято</b>\n\n"
        "На жаль, без прийняття умов використання ви не можете користуватися ботом.\n"
        "Якщо передумаєте, натисніть /start знову."
    )
    await callback.answer("Умови не прийнято")

# -------------------------------
# Main Menu Handlers
# -------------------------------
@dp.callback_query(F.data == "main_order")
async def main_order(callback: CallbackQuery):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT name FROM cities")
            cities = [row[0] for row in await cursor.fetchall()]

        if not cities:
            cities = ["Київ", "Дніпро", "Львів"]

        # Check if user has items in cart from another city
        user_cart_city = await get_user_cart_city(callback.from_user.id)
        
        kb = InlineKeyboardBuilder()
        for city in cities:
            # If user has cart items from another city, disable other cities
            if user_cart_city and user_cart_city[1] != city:
                kb.button(text=f"🚫 {city} (очистіть кошик)", callback_data="cart_city_conflict")
            else:
                kb.button(text=city, callback_data=f"city:{city}")
        kb.button(text="🔙 Назад", callback_data="back_to_main")
        kb.adjust(2)

        cart_warning = ""
        if user_cart_city:
            cart_warning = f"\n\n⚠️ У вашому кошику є товари з міста {user_cart_city[1]}. Ви можете замовляти тільки з одного міста за раз."

        await callback.message.edit_text(
            f"🏙️ Оберіть своє місто:{cart_warning}",
            reply_markup=kb.as_markup()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in main_order: {e}")
        await callback.answer("❌ Помилка")

@dp.callback_query(F.data == "cart_city_conflict")
async def cart_city_conflict(callback: CallbackQuery):
    await callback.answer("❌ Спочатку очистіть кошик або оформіть замовлення", show_alert=True)

@dp.callback_query(F.data == "main_cart")
async def show_cart(callback: CallbackQuery):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT c.id, p.name, p.price, c.quantity, p.photo, p.id as product_id, ct.name as city_name
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
                "🛍️ <b>Ваш кошик порожній</b>\n\n"
                "Додайте товари для замовлення!",
                reply_markup=kb.as_markup()
            )
            await callback.answer()
            return
        
        total_price = sum(item[2] * item[3] for item in cart_items)
        city_name = cart_items[0][6]  # All items should be from the same city
        cart_text = f"🛍️ <b>Ваш кошик ({city_name}):</b>\n\n"
        
        for cart_id, name, price, quantity, photo, product_id, _ in cart_items:
            cart_text += f"📦 <b>{name}</b>\n"
            cart_text += f"💵 {price} грн × {quantity} шт = {price * quantity} грн\n\n"
        
        cart_text += f"💰 <b>Всього: {total_price} грн</b>"
        
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Оформити замовлення", callback_data="cart_checkout")
        kb.button(text="🗑️ Очистити кошик", callback_data="cart_clear")
        kb.button(text="🔙 Назад", callback_data="back_to_main")
        kb.adjust(1)
        
        await callback.message.edit_text(cart_text, reply_markup=kb.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error showing cart: {e}")
        await callback.answer("❌ Помилка")

@dp.callback_query(F.data == "main_feedback")
async def main_feedback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserFeedbackState.waiting_for_feedback)
    await callback.message.edit_text(
        "💬 <b>Відправити відгук</b>\n\n"
        "Напишіть свій відгук або пропозицію. Ваше повідомлення буде передано менеджерам магазину."
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text(
        "🌸 Оберіть дію:",
        reply_markup=await get_main_menu_keyboard()
    )
    await callback.answer()

# -------------------------------
# User Feedback Handler
# -------------------------------
@dp.message(UserFeedbackState.waiting_for_feedback, F.text)
async def receive_user_feedback(message: Message, state: FSMContext):
    try:
        feedback_text = message.text.strip()
        user = message.from_user
        
        # Get user's full name safely
        first_name = user.first_name or ""
        last_name = user.last_name or ""
        full_name = f"{first_name} {last_name}".strip() or "Користувач"
        
        feedback_message = (
            f"💬 <b>НОВИЙ ВІДГУК КЛІЄНТА</b>\n\n"
            f"👤 Від: {full_name}\n"
            f"🆔 ID: <a href='tg://user?id={user.id}'>{user.id}</a>\n"
            f"👨‍💻 Username: @{user.username or 'немає'}\n\n"
            f"💬 <b>Текст відгуку:</b>\n{feedback_text}"
        )
        
        success = await safe_send_message(
            MANAGER_CHAT_ID,
            feedback_message,
            parse_mode=ParseMode.HTML
        )
        
        if success:
            await message.answer(
                "✅ <b>Дякуємо за відгук!</b>\n\n"
                "Ваше повідомлення успішно передано менеджерам.",
                reply_markup=await get_main_menu_keyboard()
            )
        else:
            await message.answer(
                "❌ <b>Помилка відправки</b>\n\n"
                "Не вдалося передати ваш відгук. Спробуйте пізніше.",
                reply_markup=await get_main_menu_keyboard()
            )
        
        await state.clear()
    except Exception as e:
        logger.error(f"Error in receive_user_feedback: {e}")
        await message.answer(
            "❌ Виникла помилка. Спробуйте пізніше.",
            reply_markup=await get_main_menu_keyboard()
        )
        await state.clear()

# -------------------------------
# Admin Panel
# -------------------------------
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Ти не адмін")
        return

    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Додати місто", callback_data="adm:add_city")
    kb.button(text="📝 Редагувати місто", callback_data="adm:edit_city")
    kb.button(text="❌ Видалити місто", callback_data="adm:delete_city")
    kb.button(text="➕ Додати товар", callback_data="adm:add_product")
    kb.button(text="📝 Редагувати товар", callback_data="adm:edit_product")
    kb.button(text="❌ Видалити товар", callback_data="adm:delete_product")
    kb.button(text="📋 Створити PDF умов", callback_data="adm:create_terms")
    kb.adjust(1)

    await message.answer("⚙️ Адмін-панель", reply_markup=kb.as_markup())

# -------------------------------
# Admin: Create Terms PDF
# -------------------------------
@dp.callback_query(F.data == "adm:create_terms")
async def create_terms_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PDFTermsState.waiting_for_content)
    await callback.message.answer(
        "📋 <b>Створення PDF з умовами</b>\n\n"
        "Надішліть текст умов використання магазину."
    )
    await callback.answer()

@dp.message(PDFTermsState.waiting_for_content, F.text)
async def create_terms_finish(message: Message, state: FSMContext):
    try:
        content = message.text.strip()
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM terms_content")
            await db.execute("INSERT INTO terms_content (content) VALUES (?)", (content,))
            await db.commit()
        
        pdf_bytes = create_terms_pdf(content)
        pdf_file = BufferedInputFile(pdf_bytes, filename="terms_preview.pdf")
        
        await message.answer_document(
            pdf_file,
            caption="✅ <b>PDF з умовами створено!</b>\n\n"
                   "Тепер всі нові користувачі отримуватимуть цей документ."
        )
        await state.clear()
    except Exception as e:
        logger.error(f"Error creating terms PDF: {e}")
        await message.answer("❌ Помилка при створенні PDF")
        await state.clear()

# -------------------------------
# Admin: Add City with Product Copying
# -------------------------------
@dp.callback_query(F.data == "adm:add_city")
async def add_city_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddCity.waiting_for_name)
    await callback.message.answer("Введи назву міста:")
    await callback.answer()

@dp.message(AddCity.waiting_for_name, F.text)
async def add_city_finish(message: Message, state: FSMContext):
    city = message.text.strip()
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT id FROM cities WHERE name=?", (city,))
            if await cursor.fetchone():
                await message.answer(f"❌ Місто <b>{city}</b> вже існує!")
                await state.clear()
                return
                
            cursor = await db.execute("INSERT INTO cities (name) VALUES (?)", (city,))
            new_city_id = cursor.lastrowid
            await db.commit()
            
            cursor = await db.execute("""
                SELECT DISTINCT c.id, c.name 
                FROM cities c 
                JOIN products p ON c.id = p.city_id 
                WHERE c.id != ?
            """, (new_city_id,))
            cities_with_products = await cursor.fetchall()
        
        if cities_with_products:
            await state.update_data(new_city_id=new_city_id, city_name=city)
            await state.set_state(AddCity.waiting_for_products)
            
            kb = InlineKeyboardBuilder()
            for city_id, city_name in cities_with_products:
                kb.button(text=f"📦 З міста {city_name}", callback_data=f"copy_from:{city_id}")
            kb.button(text="❌ Не копіювати товари", callback_data="no_copy_products")
            kb.adjust(1)
            
            await message.answer(
                f"🏙 Місто <b>{city}</b> додано!\n\n"
                f"Хочете скопіювати товари з інших міст?",
                reply_markup=kb.as_markup()
            )
        else:
            await message.answer(f"🏙 Місто <b>{city}</b> додано!")
            await state.clear()
            
    except Exception as e:
        logger.error(f"Error adding city: {e}")
        await message.answer("❌ Помилка при додаванні міста")
        await state.clear()

@dp.callback_query(F.data.startswith("copy_from:"), AddCity.waiting_for_products)
async def copy_products_from_city(callback: CallbackQuery, state: FSMContext):
    try:
        source_city_id = int(callback.data.split(":")[1])
        data = await state.get_data()
        new_city_id = data["new_city_id"]
        city_name = data["city_name"]
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT name, description, price, photo 
                FROM products 
                WHERE city_id = ?
            """, (source_city_id,))
            products = await cursor.fetchall()
            
            copied_count = 0
            for name, description, price, photo in products:
                await db.execute("""
                    INSERT INTO products (city_id, name, description, price, photo)
                    VALUES (?, ?, ?, ?, ?)
                """, (new_city_id, name, description, price, photo))
                copied_count += 1
            
            await db.commit()
            
            cursor = await db.execute("SELECT name FROM cities WHERE id=?", (source_city_id,))
            source_city_name = (await cursor.fetchone())[0]
        
        await callback.message.edit_text(
            f"✅ <b>Місто {city_name} створено!</b>\n\n"
            f"Скопійовано {copied_count} товарів з міста {source_city_name}"
        )
        await state.clear()
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error copying products: {e}")
        await callback.answer("❌ Помилка при копіюванні товарів")
        await state.clear()

@dp.callback_query(F.data == "no_copy_products", AddCity.waiting_for_products)
async def no_copy_products(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    city_name = data["city_name"]
    
    await callback.message.edit_text(f"✅ Місто <b>{city_name}</b> створено без товарів!")
    await state.clear()
    await callback.answer()

# -------------------------------
# Admin: Edit/Delete City
# -------------------------------
@dp.callback_query(F.data == "adm:edit_city")
async def edit_city_start(callback: CallbackQuery, state: FSMContext):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT id, name FROM cities")
            cities = await cursor.fetchall()
        if not cities:
            await callback.message.answer("❌ Міст нема")
            return
        kb = InlineKeyboardBuilder()
        for cid, name in cities:
            kb.button(text=name, callback_data=f"edit_city:{cid}")
        kb.adjust(2)
        await callback.message.answer("Оберіть місто для редагування:", reply_markup=kb.as_markup())
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in edit_city_start: {e}")
        await callback.message.answer("❌ Помилка при завантаженні міст")

@dp.message(OrderStates.waiting_for_area, F.text)
async def order_area(message: Message, state: FSMContext):
    await state.update_data(area=message.text.strip())
    await state.set_state(OrderStates.waiting_for_comment)
    await message.answer("📝 Можеш залишити коментар (або напиши '-' якщо немає):")

@dp.message(OrderStates.waiting_for_comment, F.text)
async def order_comment(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        phone = data["phone"]
        area = data["area"]
        comment = message.text.strip()
        uid = data["user_id"]
        
        if data.get("is_cart_order"):
            # Cart order processing
            cart_items = data["cart_items"]
            total_price = sum(item[3] * item[1] for item in cart_items)
            city_name = cart_items[0][4]  # Get city name from cart items
            
            async with aiosqlite.connect(DB_PATH) as db:
                # Create separate orders for each product in cart
                order_ids = []
                for product_id, quantity, name, price, _ in cart_items:
                    for _ in range(quantity):
                        cur = await db.execute(
                            "INSERT INTO orders (user_id, product_id, phone, area, comment, status) "
                            "VALUES (?, ?, ?, ?, ?, 'pending')",
                            (uid, product_id, phone, area, comment)
                        )
                        order_ids.append(cur.lastrowid)
                
                await db.commit()
                
                # Clear cart
                await db.execute("DELETE FROM cart WHERE user_id=?", (uid,))
                await db.commit()
            
            # Prepare cart order message
            order_text = f"🆕 НОВЕ ЗАМОВЛЕННЯ (КОШИК) #{'-'.join(map(str, order_ids))}\n\n"
            
            username = message.from_user.username or "немає"
            first_name = message.from_user.first_name or ""
            last_name = message.from_user.last_name or ""
            full_name = f"{first_name} {last_name}".strip() or "Немає імені"
            
            order_text += (
                f"👤 Клієнт: {full_name}\n"
                f"🆔 ID: <a href='tg://user?id={uid}'>{uid}</a>\n"
                f"👨‍💻 Username: @{username}\n"
                f"🏙️ Місто: {city_name}\n"
                f"📱 Телефон: {phone}\n"
                f"🏘 Район: {area}\n"
                f"📝 Коментар: {comment}\n\n"
                f"📦 <b>ТОВАРИ:</b>\n"
            )
            
            for product_id, quantity, name, price, _ in cart_items:
                subtotal = price * quantity
                order_text += f"• {name} × {quantity} шт = {subtotal} грн\n"
            
            order_text += f"\n💰 <b>ВСЬОГО: {total_price} грн</b>\n📌 Статус: Очікує підтвердження"
            
            kb = InlineKeyboardBuilder()
            kb.button(text="✅ Прийняти", callback_data=f"order_accept:{order_ids[0]}")
            kb.button(text="❌ Відхилити", callback_data=f"order_reject:{order_ids[0]}")
            kb.adjust(2)
            
        else:
            # Single product order processing
            pid = data["product_id"]
            
            async with aiosqlite.connect(DB_PATH) as db:
                cur = await db.execute(
                    "INSERT INTO orders (user_id, product_id, phone, area, comment, status) "
                    "VALUES (?, ?, ?, ?, ?, 'pending')",
                    (uid, pid, phone, area, comment)
                )
                order_id = cur.lastrowid
                await db.commit()

                cur = await db.execute("""
                    SELECT p.name, p.price, c.name as city_name 
                    FROM products p
                    JOIN cities c ON p.city_id = c.id
                    WHERE p.id=?
                """, (pid,))
                product = await cur.fetchone()
            
            username = message.from_user.username or "немає"
            first_name = message.from_user.first_name or ""
            last_name = message.from_user.last_name or ""
            full_name = f"{first_name} {last_name}".strip() or "Немає імені"

            order_text = (
                f"🆕 НОВЕ ЗАМОВЛЕННЯ #{order_id}\n\n"
                f"👤 Клієнт: {full_name}\n"
                f"🆔 ID: <a href='tg://user?id={uid}'>{uid}</a>\n"
                f"👨‍💻 Username: @{username}\n"
                f"🏙️ Місто: {product[2]}\n"
                f"📦 Товар: {product[0]}\n"
                f"💵 Ціна: {product[1]:.2f} грн\n"
                f"📱 Телефон: {phone}\n"
                f"🏘 Район: {area}\n"
                f"📝 Коментар: {comment}\n"
                f"📌 Статус: Очікує підтвердження"
            )

            kb = InlineKeyboardBuilder()
            kb.button(text="✅ Прийняти", callback_data=f"order_accept:{order_id}")
            kb.button(text="❌ Відхилити", callback_data=f"order_reject:{order_id}")
            kb.adjust(2)

        # Notify client first
        await message.answer(
            "✅ Замовлення оформлено! Менеджер скоро зв'яжеться з тобою.",
            reply_markup=await get_main_menu_keyboard()
        )
        await state.clear()

        # Send to manager with retry logic
        success = await safe_send_message(
            MANAGER_CHAT_ID, 
            order_text, 
            reply_markup=kb.as_markup(),
            parse_mode=ParseMode.HTML
        )
        
        if not success:
            logger.error(f"Failed to send order to manager")
            for admin_id in ADMIN_IDS:
                await safe_send_message(
                    admin_id,
                    f"⚠️ Не вдалося відправити замовлення менеджеру!\n\n{order_text}"
                )

    except Exception as e:
        logger.error(f"Error in order_comment: {e}")
        await message.answer(
            "❌ Виникла помилка при оформленні замовлення. Спробуйте ще раз.",
            reply_markup=await get_main_menu_keyboard()
        )
        await state.clear()

# -------------------------------
# Manager: Accept / Reject with Feedback
# -------------------------------
@dp.callback_query(F.data.startswith("order_accept:"))
async def accept_order(callback: CallbackQuery, state: FSMContext):
    try:
        order_id = int(callback.data.split(":")[1])
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT o.user_id, p.name 
                FROM orders o
                LEFT JOIN products p ON o.product_id = p.id
                WHERE o.id = ?
            """, (order_id,))
            order_data = await cursor.fetchone()
        
        if not order_data:
            await callback.answer("❌ Замовлення не знайдено")
            return
        
        user_id, product_name = order_data
        product_name = product_name or "Замовлення з кошика"
        
        await state.update_data(order_id=order_id, user_id=user_id, product_name=product_name, action='accept')
        await state.set_state(FeedbackStates.waiting_for_accept_message)
        
        await callback.message.answer(
            f"✅ Замовлення #{order_id} буде прийнято.\n"
            f"Напишіть повідомлення для клієнта (або '-' для стандартного):"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error accepting order: {e}")
        await callback.answer("❌ Помилка при прийнятті замовлення")

@dp.message(FeedbackStates.waiting_for_accept_message, F.text)
async def send_accept_feedback(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        order_id = data["order_id"]
        user_id = data["user_id"]
        product_name = data["product_name"]
        custom_message = message.text.strip()
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE orders SET status='accepted' WHERE id=?", (order_id,))
            await db.commit()
        
        if custom_message == '-':
            client_message = (
                f"✅ <b>Ваше замовлення прийнято!</b>\n\n"
                f"📦 Товар: {product_name}\n"
                f"🆔 Номер замовлення: #{order_id}\n\n"
                f"Дякуємо за покупку! Скоро з вами зв'яжуться для уточнення деталей доставки."
            )
        else:
            client_message = (
                f"✅ <b>Ваше замовлення прийнято!</b>\n\n"
                f"📦 Товар: {product_name}\n"
                f"🆔 Номер замовлення: #{order_id}\n\n"
                f"💬 Повідомлення від менеджера:\n{custom_message}"
            )
        
        success = await safe_send_message(user_id, client_message, parse_mode=ParseMode.HTML)
        
        if success:
            await message.answer(f"✅ Замовлення #{order_id} прийнято і клієнта повідомлено!")
        else:
            await message.answer(f"✅ Замовлення #{order_id} прийнято, але не вдалося повідомити клієнта")
        
        await state.clear()
    except Exception as e:
        logger.error(f"Error sending accept feedback: {e}")
        await message.answer("❌ Помилка при відправці повідомлення")
        await state.clear()

@dp.callback_query(F.data.startswith("order_reject:"))
async def reject_order(callback: CallbackQuery, state: FSMContext):
    try:
        order_id = int(callback.data.split(":")[1])
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT o.user_id, p.name 
                FROM orders o
                LEFT JOIN products p ON o.product_id = p.id
                WHERE o.id = ?
            """, (order_id,))
            order_data = await cursor.fetchone()
        
        if not order_data:
            await callback.answer("❌ Замовлення не знайдено")
            return
        
        user_id, product_name = order_data
        product_name = product_name or "Замовлення з кошика"
        
        await state.update_data(order_id=order_id, user_id=user_id, product_name=product_name, action='reject')
        await state.set_state(FeedbackStates.waiting_for_reject_reason)
        
        await callback.message.answer(
            f"❌ Замовлення #{order_id} буде відхилено.\n"
            f"Напишіть причину відхилення для клієнта:"
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error rejecting order: {e}")
        await callback.answer("❌ Помилка при відхиленні замовлення")

@dp.message(FeedbackStates.waiting_for_reject_reason, F.text)
async def send_reject_feedback(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        order_id = data["order_id"]
        user_id = data["user_id"]
        product_name = data["product_name"]
        reason = message.text.strip()
        
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE orders SET status='rejected' WHERE id=?", (order_id,))
            await db.commit()
        
        client_message = (
            f"❌ <b>На жаль, ваше замовлення відхилено</b>\n\n"
            f"📦 Товар: {product_name}\n"
            f"🆔 Номер замовлення: #{order_id}\n\n"
            f"💬 Причина відхилення:\n{reason}\n\n"
            f"Ви можете оформити нове замовлення або зв'язатися з нами для уточнень."
        )
        
        success = await safe_send_message(user_id, client_message, parse_mode=ParseMode.HTML)
        
        if success:
            await message.answer(f"❌ Замовлення #{order_id} відхилено і клієнта повідомлено")
        else:
            await message.answer(f"❌ Замовлення #{order_id} відхилено, але не вдалося повідомити клієнта")
        
        await state.clear()
    except Exception as e:
        logger.error(f"Error sending reject feedback: {e}")
        await message.answer("❌ Помилка при відправці повідомлення")
        await state.clear()

# -------------------------------
# Error Handler
# -------------------------------
@dp.error()
async def error_handler(event, exception):
    logger.error(f"Error occurred: {exception}")
    return True

# -------------------------------
# Main Function
# -------------------------------
async def main():
    try:
        await init_db()
        logger.info("Starting bot polling...")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())

@dp.callback_query(F.data.startswith("edit_city:"))
async def edit_city_choose(callback: CallbackQuery, state: FSMContext):
    city_id = int(callback.data.split(":")[1])
    await state.update_data(city_id=city_id)
    await state.set_state(EditCity.waiting_for_new_name)
    await callback.message.answer("Введіть нову назву міста:")
    await callback.answer()

@dp.message(EditCity.waiting_for_new_name, F.text)
async def edit_city_finish(message: Message, state: FSMContext):
    new_name = message.text.strip()
    data = await state.get_data()
    city_id = data["city_id"]
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE cities SET name=? WHERE id=?", (new_name, city_id))
            await db.commit()
        await message.answer(f"🏙 Місто оновлено: {new_name}")
        await state.clear()
    except Exception as e:
        logger.error(f"Error updating city: {e}")
        await message.answer("❌ Помилка при оновленні міста")
        await state.clear()

@dp.callback_query(F.data == "adm:delete_city")
async def delete_city_start(callback: CallbackQuery):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT id, name FROM cities")
            cities = await cursor.fetchall()
        if not cities:
            await callback.message.answer("❌ Міст нема")
            return
        kb = InlineKeyboardBuilder()
        for cid, name in cities:
            kb.button(text=name, callback_data=f"delete_city:{cid}")
        kb.adjust(2)
        await callback.message.answer("Оберіть місто для видалення:", reply_markup=kb.as_markup())
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in delete_city_start: {e}")
        await callback.message.answer("❌ Помилка при завантаженні міст")

@dp.callback_query(F.data.startswith("delete_city:"))
async def delete_city(callback: CallbackQuery):
    city_id = int(callback.data.split(":")[1])
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM cities WHERE id=?", (city_id,))
            await db.execute("DELETE FROM products WHERE city_id=?", (city_id,))
            await db.commit()
        await callback.message.answer("✅ Місто та всі товари видалено!")
        await callback.answer()
    except Exception as e:
        logger.error(f"Error deleting city: {e}")
        await callback.message.answer("❌ Помилка при видаленні міста")

# -------------------------------
# Admin: Add Product to Multiple Cities
# -------------------------------
@dp.callback_query(F.data == "adm:add_product")
async def add_product_start(callback: CallbackQuery, state: FSMContext):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT id, name FROM cities")
            cities = await cursor.fetchall()
        
        if not cities:
            await callback.message.answer("❌ Спочатку додайте міста")
            return
            
        kb = InlineKeyboardBuilder()
        for cid, name in cities:
            kb.button(text=f"☐ {name}", callback_data=f"city_select:{cid}")
        kb.button(text="✅ Підтвердити вибір", callback_data="cities_confirmed")
        kb.adjust(2)
        
        await state.update_data(selected_cities=set())
        await state.set_state(AddProduct.cities)
        await callback.message.answer("Оберіть міста для товару (можна вибрати кілька):", reply_markup=kb.as_markup())
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in add_product_start: {e}")
        await callback.message.answer("❌ Помилка при завантаженні міст")

@dp.callback_query(F.data.startswith("city_select:"), AddProduct.cities)
async def toggle_city_selection(callback: CallbackQuery, state: FSMContext):
    city_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    selected_cities = data.get('selected_cities', set())
    
    if city_id in selected_cities:
        selected_cities.remove(city_id)
    else:
        selected_cities.add(city_id)
    
    await state.update_data(selected_cities=selected_cities)
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT id, name FROM cities")
            cities = await cursor.fetchall()
        
        kb = InlineKeyboardBuilder()
        for cid, name in cities:
            if cid in selected_cities:
                kb.button(text=f"☑️ {name}", callback_data=f"city_select:{cid}")
            else:
                kb.button(text=f"☐ {name}", callback_data=f"city_select:{cid}")
        kb.button(text="✅ Підтвердити вибір", callback_data="cities_confirmed")
        kb.adjust(2)
        
        await callback.message.edit_reply_markup(reply_markup=kb.as_markup())
        await callback.answer(f"{'Вибрано' if city_id in selected_cities else 'Скасовано'}")
    except Exception as e:
        logger.error(f"Error updating city selection: {e}")
        await callback.answer("❌ Помилка")

@dp.callback_query(F.data == "cities_confirmed", AddProduct.cities)
async def confirm_cities_selection(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_cities = data.get('selected_cities', set())
    
    if not selected_cities:
        await callback.answer("❌ Оберіть хоча б одне місто")
        return
    
    await state.set_state(AddProduct.photo)
    await callback.message.answer(f"Вибрано міст: {len(selected_cities)}\nНадішли фото товару:")
    await callback.answer()

@dp.message(AddProduct.photo, F.photo)
async def add_product_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(photo=file_id)
    await state.set_state(AddProduct.name)
    await message.answer("Введи назву товару:")

@dp.message(AddProduct.name, F.text)
async def add_product_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddProduct.description)
    await message.answer("Введи опис товару:")

@dp.message(AddProduct.description, F.text)
async def add_product_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(AddProduct.price)
    await message.answer("Введи ціну (числом):")

@dp.message(AddProduct.price, F.text)
async def add_product_price(message: Message, state: FSMContext):
    data = await state.get_data()
    selected_cities, photo, name, desc = data["selected_cities"], data["photo"], data["name"], data["description"]
    try:
        price = float(message.text.strip())
    except ValueError:
        await message.answer("❌ Невірна ціна, введи числом")
        return

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            city_names = []
            for city_id in selected_cities:
                cursor = await db.execute("SELECT name FROM cities WHERE id=?", (city_id,))
                row = await cursor.fetchone()
                if row:
                    city_names.append(row[0])
                    await db.execute("""
                        INSERT INTO products (city_id, name, description, price, photo)
                        VALUES (?, ?, ?, ?, ?)""",
                        (city_id, name, desc, price, photo))
            
            await db.commit()

        cities_text = ", ".join(city_names)
        await message.answer(f"✅ Товар <b>{name}</b> додано в міста: {cities_text}!")
        await state.clear()
    except Exception as e:
        logger.error(f"Error adding product to multiple cities: {e}")
        await message.answer("❌ Помилка при додаванні товару")
        await state.clear()

# -------------------------------
# Admin: Edit Product (Fixed to edit globally by name)
# -------------------------------
@dp.callback_query(F.data == "adm:edit_product")
async def edit_product_start(callback: CallbackQuery, state: FSMContext):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT DISTINCT name FROM products ORDER BY name")
            product_names = await cursor.fetchall()
        if not product_names:
            await callback.message.answer("❌ Товарів нема")
            return
        kb = InlineKeyboardBuilder()
        for name_tuple in product_names:
            name = name_tuple[0]
            kb.button(text=name, callback_data=f"edit_product_name:{name}")
        kb.adjust(1)
        await callback.message.answer("Оберіть товар для редагування:", reply_markup=kb.as_markup())
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in edit_product_start: {e}")
        await callback.message.answer("❌ Помилка при завантаженні товарів")

@dp.callback_query(F.data.startswith("edit_product_name:"))
async def edit_product_choose(callback: CallbackQuery, state: FSMContext):
    product_name = callback.data.split(":", 1)[1]
    await state.update_data(product_name=product_name)
    kb = InlineKeyboardBuilder()
    kb.button(text="Назва", callback_data="field:name")
    kb.button(text="Опис", callback_data="field:description")
    kb.button(text="Ціна", callback_data="field:price")
    kb.adjust(1)
    await callback.message.answer(f"Що хочеш редагувати в товарі '{product_name}'?", reply_markup=kb.as_markup())
    await state.set_state(EditProduct.waiting_for_field)
    await callback.answer()

@dp.callback_query(F.data.startswith("field:"), EditProduct.waiting_for_field)
async def edit_product_field(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split(":")[1]
    await state.update_data(field=field)
    await state.set_state(EditProduct.waiting_for_value)
    await callback.message.answer(f"Введіть нове значення для {field}:")
    await callback.answer()

@dp.message(EditProduct.waiting_for_value, F.text)
async def edit_product_value(message: Message, state: FSMContext):
    data = await state.get_data()
    product_name = data["product_name"]
    field = data["field"]
    value = message.text.strip()
    
    if field == "price":
        try:
            value = float(value)
        except ValueError:
            await message.answer("❌ Невірна ціна")
            return
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(f"SELECT COUNT(*) FROM products WHERE name=?", (product_name,))
            count_before = (await cursor.fetchone())[0]
            
            # Update ALL products with this name across all cities
            await db.execute(f"UPDATE products SET {field}=? WHERE name=?", (value, product_name))
            await db.commit()
            
            cursor = await db.execute(f"SELECT COUNT(*) FROM products WHERE name=?", (product_name,))
            count_after = (await cursor.fetchone())[0]
        
        await message.answer(f"✅ Товар '{product_name}' оновлено в {count_after} містах!")
        await state.clear()
    except Exception as e:
        logger.error(f"Error updating product: {e}")
        await message.answer("❌ Помилка при оновленні товару")
        await state.clear()

# -------------------------------
# Admin: Delete Product
# -------------------------------
@dp.callback_query(F.data == "adm:delete_product")
async def delete_product_start(callback: CallbackQuery, state: FSMContext):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT DISTINCT name FROM products ORDER BY name")
            products = await cursor.fetchall()
        
        if not products:
            await callback.message.answer("❌ Товарів нема")
            return
            
        kb = InlineKeyboardBuilder()
        for name_tuple in products:
            name = name_tuple[0]
            display_name = name[:30] + "..." if len(name) > 30 else name
            kb.button(text=display_name, callback_data=f"del_product_name:{name}")
        
        kb.adjust(1)
        await callback.message.answer("Оберіть товар для видалення:", reply_markup=kb.as_markup())
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in delete_product_start: {e}")
        await callback.message.answer("❌ Помилка при завантаженні товарів")

@dp.callback_query(F.data.startswith("del_product_name:"))
async def delete_product_show_cities(callback: CallbackQuery, state: FSMContext):
    product_name = callback.data.split(":", 1)[1]
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT p.id, c.name, c.id as city_id
                FROM products p
                JOIN cities c ON p.city_id = c.id
                WHERE p.name = ?
                ORDER BY c.name
            """, (product_name,))
            product_cities = await cursor.fetchall()
        
        if not product_cities:
            await callback.message.answer("❌ Товар не знайдено")
            return
        
        await state.update_data(product_name=product_name, selected_for_deletion=set())
        await state.set_state(DeleteProduct.waiting_for_cities)
        
        kb = InlineKeyboardBuilder()
        for pid, city_name, city_id in product_cities:
            kb.button(text=f"☐ {city_name}", callback_data=f"del_city_select:{city_id}")
        kb.button(text="🗑️ Видалити з обраних міст", callback_data="confirm_deletion")
        kb.button(text="🗑️ Видалити з усіх міст", callback_data="delete_all_cities")
        kb.adjust(2)
        
        await callback.message.answer(
            f"Товар '<b>{product_name}</b>' знайдено в містах:\n"
            f"Оберіть міста, з яких хочете видалити товар:",
            reply_markup=kb.as_markup()
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Error showing cities for deletion: {e}")
        await callback.message.answer("❌ Помилка")

@dp.callback_query(F.data.startswith("del_city_select:"), DeleteProduct.waiting_for_cities)
async def toggle_city_for_deletion(callback: CallbackQuery, state: FSMContext):
    city_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    product_name = data["product_name"]
    selected_for_deletion = data.get('selected_for_deletion', set())
    
    if city_id in selected_for_deletion:
        selected_for_deletion.remove(city_id)
    else:
        selected_for_deletion.add(city_id)
    
    await state.update_data(selected_for_deletion=selected_for_deletion)
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT p.id, c.name, c.id as city_id
                FROM products p
                JOIN cities c ON p.city_id = c.id
                WHERE p.name = ?
                ORDER BY c.name
            """, (product_name,))
            product_cities = await cursor.fetchall()
        
        kb = InlineKeyboardBuilder()
        for pid, city_name, city_id_db in product_cities:
            if city_id_db in selected_for_deletion:
                kb.button(text=f"☑️ {city_name}", callback_data=f"del_city_select:{city_id_db}")
            else:
                kb.button(text=f"☐ {city_name}", callback_data=f"del_city_select:{city_id_db}")
        kb.button(text="🗑️ Видалити з обраних міст", callback_data="confirm_deletion")
        kb.button(text="🗑️ Видалити з усіх міст", callback_data="delete_all_cities")
        kb.adjust(2)
        
        await callback.message.edit_reply_markup(reply_markup=kb.as_markup())
        await callback.answer(f"{'Обрано' if city_id in selected_for_deletion else 'Скасовано'}")
    except Exception as e:
        logger.error(f"Error updating deletion selection: {e}")
        await callback.answer("❌ Помилка")

@dp.callback_query(F.data == "confirm_deletion", DeleteProduct.waiting_for_cities)
async def confirm_partial_deletion(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_name = data["product_name"]
    selected_for_deletion = data.get('selected_for_deletion', set())
    
    if not selected_for_deletion:
        await callback.answer("❌ Оберіть хоча б одне місто")
        return
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            deleted_cities = []
            for city_id in selected_for_deletion:
                cursor = await db.execute("SELECT name FROM cities WHERE id=?", (city_id,))
                row = await cursor.fetchone()
                if row:
                    deleted_cities.append(row[0])
                
                await db.execute("DELETE FROM products WHERE name=? AND city_id=?", (product_name, city_id))
            
            await db.commit()
        
        cities_text = ", ".join(deleted_cities)
        await callback.message.answer(f"✅ Товар '<b>{product_name}</b>' видалено з міст: {cities_text}")
        await state.clear()
        await callback.answer()
    except Exception as e:
        logger.error(f"Error deleting product from cities: {e}")
        await callback.message.answer("❌ Помилка при видаленні товару")
        await state.clear()

@dp.callback_query(F.data == "delete_all_cities", DeleteProduct.waiting_for_cities)
async def delete_from_all_cities(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_name = data["product_name"]
    
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM products WHERE name=?", (product_name,))
            await db.commit()
        
        await callback.message.answer(f"✅ Товар '<b>{product_name}</b>' видалено з усіх міст!")
        await state.clear()
        await callback.answer()
    except Exception as e:
        logger.error(f"Error deleting product from all cities: {e}")
        await callback.message.answer("❌ Помилка при видаленні товару")
        await state.clear()

# -------------------------------
# Client: Select City & Products
# -------------------------------
@dp.callback_query(F.data.startswith("city:"))
async def select_city(callback: CallbackQuery):
    city = callback.data.split(":")[1]
    await callback.answer(f"Ти вибрав {city}")

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id, name, price, description, photo FROM products "
                "WHERE city_id=(SELECT id FROM cities WHERE name=?)", (city,)
            )
            products = await cursor.fetchall()

        if not products:
            await callback.message.answer("У цьому місті поки немає товарів 🌱")
            return

        for pid, name, price, desc, photo in products:
            kb = InlineKeyboardBuilder()
            kb.button(text="🛒 Додати в кошик", callback_data=f"add_to_cart:{pid}")
            kb.button(text="⚡ Замовити зараз", callback_data=f"buy:{pid}")
            kb.adjust(2)
            
            caption = f"<b>{name}</b>\n{desc}\n💵 {price} грн"
            
            try:
                if photo:
                    await callback.message.answer_photo(
                        photo,
                        caption=caption,
                        reply_markup=kb.as_markup()
                    )
                else:
                    await callback.message.answer(
                        caption,
                        reply_markup=kb.as_markup()
                    )
            except Exception as e:
                logger.error(f"Error sending product {pid}: {e}")
                await callback.message.answer(
                    caption,
                    reply_markup=kb.as_markup()
                )
        
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 Назад до меню", callback_data="back_to_main")
        kb.adjust(1)
        
        await callback.message.answer(
            "🌸 Оберіть товар зі списку вище або поверніться до меню:",
            reply_markup=kb.as_markup()
        )
    except Exception as e:
        logger.error(f"Error in select_city: {e}")
        await callback.message.answer("❌ Помилка при завантаженні товарів")

# -------------------------------
# Cart Management (with quantity selection)
# -------------------------------
@dp.callback_query(F.data.startswith("add_to_cart:"))
async def add_to_cart(callback: CallbackQuery, state: FSMContext):
    try:
        product_id = int(callback.data.split(":")[1])
        user_id = callback.from_user.id
        
        # Check if user has items from another city
        user_cart_city = await get_user_cart_city(user_id)
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT c.name FROM products p
                JOIN cities c ON p.city_id = c.id
                WHERE p.id = ?
            """, (product_id,))
            product_city = await cursor.fetchone()
            
            if user_cart_city and user_cart_city[1] != product_city[0]:
                await callback.answer("❌ У кошику вже є товари з іншого міста. Спочатку очистіть кошик!", show_alert=True)
                return
            
            cursor = await db.execute("SELECT name FROM products WHERE id=?", (product_id,))
            product_name = (await cursor.fetchone())[0]
        
        await state.update_data(product_id=product_id, product_name=product_name)
        await state.set_state(CartQuantityState.waiting_for_quantity)
        
        await callback.message.answer(
            f"📦 <b>{product_name}</b>\n\n"
            f"Скільки штук хочете додати в кошик? (введіть число від 1 до 10)"
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in add_to_cart: {e}")
        await callback.answer("❌ Помилка при додаванні в кошик")

@dp.message(CartQuantityState.waiting_for_quantity, F.text)
async def add_to_cart_with_quantity(message: Message, state: FSMContext):
    try:
        quantity = int(message.text.strip())
        if quantity < 1 or quantity > 10:
            await message.answer("❌ Кількість повинна бути від 1 до 10")
            return
        
        data = await state.get_data()
        product_id = data["product_id"]
        product_name = data["product_name"]
        user_id = message.from_user.id
        
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT id, quantity FROM cart 
                WHERE user_id=? AND product_id=?
            """, (user_id, product_id))
            existing = await cursor.fetchone()
            
            if existing:
                new_quantity = existing[1] + quantity
                await db.execute("""
                    UPDATE cart SET quantity=? WHERE id=?
                """, (new_quantity, existing[0]))
            else:
                await db.execute("""
                    INSERT INTO cart (user_id, product_id, quantity)
                    VALUES (?, ?, ?)
                """, (user_id, product_id, quantity))
            
            await db.commit()
        
        kb = InlineKeyboardBuilder()
        kb.button(text="🛍️ Перейти в кошик", callback_data="main_cart")
        kb.button(text="➕ Продовжити покупки", callback_data="main_order")
        kb.adjust(1)
        
        await message.answer(
            f"✅ <b>Товар додано в кошик!</b>\n\n"
            f"📦 {product_name} × {quantity} шт",
            reply_markup=kb.as_markup()
        )
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Введіть коректне число від 1 до 10")
    except Exception as e:
        logger.error(f"Error adding to cart with quantity: {e}")
        await message.answer("❌ Помилка при додаванні в кошик")
        await state.clear()

@dp.callback_query(F.data == "cart_clear")
async def clear_cart(callback: CallbackQuery):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM cart WHERE user_id=?", (callback.from_user.id,))
            await db.commit()
        
        await callback.message.edit_text(
            "🗑️ <b>Кошик очищено!</b>\n\n"
            "Ваш кошик тепер порожній.",
            reply_markup=await get_main_menu_keyboard()
        )
        await callback.answer("Кошик очищено")
        
    except Exception as e:
        logger.error(f"Error clearing cart: {e}")
        await callback.answer("❌ Помилка")

@dp.callback_query(F.data == "cart_checkout")
async def cart_checkout(callback: CallbackQuery, state: FSMContext):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("""
                SELECT c.product_id, c.quantity, p.name, p.price, ct.name as city_name
                FROM cart c
                JOIN products p ON c.product_id = p.id
                JOIN cities ct ON p.city_id = ct.id
                WHERE c.user_id = ?
            """, (callback.from_user.id,))
            cart_items = await cursor.fetchall()
        
        if not cart_items:
            await callback.answer("❌ Кошик порожній")
            return
        
        await state.update_data(
            cart_items=cart_items,
            user_id=callback.from_user.id,
            is_cart_order=True
        )
        await state.set_state(OrderStates.waiting_for_phone)
        
        await callback.message.edit_text(
            "📱 <b>Оформлення замовлення</b>\n\n"
            "Введіть свій номер телефону (0XXXXXXXXX або +380XXXXXXXXX):"
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in cart checkout: {e}")
        await callback.answer("❌ Помилка")

# -------------------------------
# Orders FSM
# -------------------------------
@dp.callback_query(F.data.startswith("buy:"))
async def buy_product(callback: CallbackQuery, state: FSMContext):
    pid = int(callback.data.split(":")[1])
    await state.update_data(product_id=pid, user_id=callback.from_user.id)
    await state.set_state(OrderStates.waiting_for_phone)
    await callback.message.answer("📱 Введи свій номер телефону (0XXXXXXXXX або +380XXXXXXXXX):")
    await callback.answer()

@dp.message(OrderStates.waiting_for_phone, F.text)
async def order_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not valid_phone(phone):
        await message.answer("❌ Невірний формат телефону. Спробуй ще раз.")
        return
    await state.update_data(phone=phone)
    await state.set_state(OrderStates.waiting_for_area)
    await message.answer("🏘 Введи свій район/адресу:")