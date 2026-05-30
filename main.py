import os
import asyncio
import logging
import aiosqlite
from datetime import datetime
from flask import Flask
from threading import Thread
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BeastBot")

# --- CONFIGURATION ---
API_ID = int(os.getenv("API_ID", "34353387"))
API_HASH = os.getenv("API_HASH", "79c65fb48e0eff802aededcef0c19d26")
USER_BOT_TOKEN = os.getenv("USER_BOT_TOKEN")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = "/data/beast_stream.db" if os.path.exists("/data") else "beast_stream.db"
PORT = int(os.getenv("PORT", "8080")) # Render's dynamic port

# --- FLASK SERVER (RENDER KE LIYE SABSE ZARURI) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Running Successfully! 🚀"

def run_web():
    logger.info(f"Starting Flask server on port {PORT}...")
    app.run(host="0.0.0.0", port=PORT)

# --- DATABASE SETUP ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, referrals INTEGER DEFAULT 0,
            watch_limit INTEGER DEFAULT 2, watched INTEGER DEFAULT 0, 
            is_premium BOOLEAN DEFAULT 0, referred_by INTEGER, 
            xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, last_active TIMESTAMP
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, thumb TEXT, 
            disk_link TEXT, app_link TEXT, category TEXT, views INTEGER DEFAULT 0, is_premium BOOLEAN DEFAULT 0
        )""")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        defaults = [('admin_user', '@Admin'), ('fs_channel', ''), ('m_mode', 'off'), ('ref_reward', '2')]
        for k, v in defaults:
            await db.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (k, v))
        await db.commit()
    logger.info("Database Initialized.")

# --- BOTS ---
user_bot = Client("user_bot", api_id=API_ID, api_hash=API_HASH, bot_token=USER_BOT_TOKEN)
admin_bot = Client("admin_bot", api_id=API_ID, api_hash=API_HASH, bot_token=ADMIN_BOT_TOKEN)

async def get_user(uid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (uid,)) as c:
            return await cursor.fetchone() if (cursor := await c.fetchone()) else None

# --- USER BOT: START HANDLER ---
@user_bot.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    # (Simple response to check if bot is working)
    await message.reply_text(f"🚀 Hello! I am online.\n\nLimit: 2 Videos Free.\nAdmin: @Admin")

# --- ADMIN BOT: START HANDLER ---
@admin_bot.on_message(filters.command("start") & filters.user(ADMIN_ID))
async def admin_start(client, message):
    await message.reply_text("👑 Admin Panel Access Granted.")

# --- MAIN RUNNER (RENDER OPTIMIZED) ---
async def main():
    # 1. Sabse pehle database ready karo
    await init_db()
    
    # 2. Bots start karo
    logger.info("Starting Bots...")
    try:
        await user_bot.start()
        await admin_bot.start()
    except Exception as e:
        logger.error(f"Error starting bots: {e}")
        return

    logger.info("SYSTEM READY 🚀")
    # 3. Bot ko zinda rakho
    await asyncio.Event().wait()

if __name__ == "__main__":
    # 4. Flask ko alag thread mein start karo SABSE PEHLE
    server_thread = Thread(target=run_web)
    server_thread.daemon = True
    server_thread.start()
    
    # 5. Async loop chalao
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
