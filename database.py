import aiosqlite
from ..config import DB_PATH

async def register_user(user_id, username, first_name, last_name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users (id, username, first_name, last_name, agreed_to_terms)
            VALUES (?, ?, ?, ?, 0)
            """,
            (user_id, username, first_name, last_name),
        )
        await db.commit()

async def get_user_cart_city(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT c.id, ct.name
            FROM cart c
            JOIN products p ON c.product_id = p.id
            JOIN cities ct ON p.city_id = ct.id
            WHERE c.user_id = ?
            LIMIT 1
        """, (user_id,))
        return await cursor.fetchone()