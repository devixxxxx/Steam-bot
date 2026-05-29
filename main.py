import os, asyncio, logging, aiosqlite, requests
from datetime import datetime
from flask import Flask
from threading import Thread
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant

# --- CONFIG ---
API_ID = int(os.getenv("API_ID", "34353387"))
API_HASH = os.getenv("API_HASH", "79c65fb48e0eff802aededcef0c19d26")
USER_BOT_TOKEN = os.getenv("USER_BOT_TOKEN")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = "/data/beast_stream.db" if os.path.exists("/data") else "beast_stream.db"

# --- LOGGING & APP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StreamingBeast")
app = Flask(__name__)

@app.route('/')
def home(): return "SYSTEM ONLINE 🚀"

def run_web():
    app.run(host="0.0.0.0", port=8080)

# --- DATABASE SETUP ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, referrals INTEGER DEFAULT 0,
            watch_limit INTEGER DEFAULT 2, watched INTEGER DEFAULT 0, 
            is_premium BOOLEAN DEFAULT 0, referred_by INTEGER, 
            xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, streak INTEGER DEFAULT 0, last_active TIMESTAMP
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, thumb TEXT, 
            disk_link TEXT, app_link TEXT, category TEXT, views INTEGER DEFAULT 0, is_premium BOOLEAN DEFAULT 0
        )""")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        defaults = [('admin_user', '@Admin'), ('fs_channel', ''), ('m_mode', 'off'), 
                    ('shortlink_api', ''), ('shortlink_url', ''), ('ref_reward', '2')]
        for k, v in defaults:
            await db.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (k, v))
        await db.commit()

# --- BOTS ---
user_bot = Client("user_bot", api_id=API_ID, api_hash=API_HASH, bot_token=USER_BOT_TOKEN)
admin_bot = Client("admin_bot", api_id=API_ID, api_hash=API_HASH, bot_token=ADMIN_BOT_TOKEN)

async def get_user(uid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (uid,)) as c: return await c.fetchone()

# --- USER HANDLERS ---
@user_bot.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    uid = message.from_user.id
    user = await get_user(uid)
    if not user:
        ref_by = int(message.command[1]) if len(message.command) > 1 and message.command[1].isdigit() else None
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO users (user_id, username, referred_by, last_active) VALUES (?,?,?,?)", 
                             (uid, message.from_user.username, ref_by, datetime.now()))
            await db.commit()
    
    btns = [[InlineKeyboardButton("🎬 Browse Videos", callback_query_data="trend")]]
    await message.reply_text(f"🚀 Hello {message.from_user.first_name}! Bot is ready.", reply_markup=InlineKeyboardMarkup(btns))

# --- ADMIN PANEL ---
@admin_bot.on_message(filters.command("start") & filters.user(ADMIN_ID))
async def admin_start(client, message):
    await message.reply_text("👑 Admin Panel Active. Use /admin to manage.")

# --- MAIN RUNNER (FIXED) ---
async def start_beast():
    await init_db()
    # Start Web Server in background
    Thread(target=run_web, daemon=True).start()
    
    # Start both bots
    await user_bot.start()
    await admin_bot.start()
    
    logger.info("SYSTEM READY 🚀")
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(start_beast())
    except (KeyboardInterrupt, SystemExit):
        pass
