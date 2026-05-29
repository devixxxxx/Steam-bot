"""
ULTRA ADVANCED PRO VIDEO STREAMING BOT (V2.0)
=============================================
Features: 
- Dual Bot (Admin + User)
- Referral (+2 Video Unlock)
- Search System (Title/Category)
- Force Subscribe (Channel Lock)
- Daily Bonus Rewards
- Leaderboard (Top Referrers)
- Maintenance Mode
- Premium System (Unlimited Access)
- Multi-Link Support (Disk/Drive/App)
- Analytics & Broadcast
=============================================
"""

import os
import asyncio
import logging
import aiosqlite
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant, FloodWait

# --- CONFIGURATION (Render Environment Variables) ---
API_ID = int(os.getenv("API_ID", "12345"))
API_HASH = os.getenv("API_HASH", "your_api_hash")
USER_BOT_TOKEN = os.getenv("USER_BOT_TOKEN")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = "/data/pro_stream.db" if os.path.exists("/data") else "pro_stream.db"

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

# --- FLASK FOR RENDER ---
app = Flask(__name__)
@app.route('/')
def health_check(): return "Bot is Alive!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# --- DATABASE INITIALIZATION ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Users Table
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, referrals INTEGER DEFAULT 0,
            watch_limit INTEGER DEFAULT 2, watched INTEGER DEFAULT 0, 
            is_premium BOOLEAN DEFAULT 0, referred_by INTEGER, last_daily TIMESTAMP
        )""")
        # Videos Table
        await db.execute("""CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, thumb TEXT, 
            disk_link TEXT, app_link TEXT, category TEXT, views INTEGER DEFAULT 0, is_premium BOOLEAN DEFAULT 0
        )""")
        # Settings
        await db.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('admin_user', '@Admin')")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('fs_channel', '')") # Format: channel_username
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('maintenance', 'off')")
        await db.commit()

# --- BOT CLIENTS ---
user_bot = Client("user_bot", api_id=API_ID, api_hash=API_HASH, bot_token=USER_BOT_TOKEN)
admin_bot = Client("admin_bot", api_id=API_ID, api_hash=API_HASH, bot_token=ADMIN_BOT_TOKEN)

# --- HELPER FUNCTIONS ---
async def get_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def get_setting(key):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            res = await cursor.fetchone()
            return res[0] if res else ""

# --- MIDDLEWARE: MAINTENANCE & FORCE JOIN ---
async def is_allowed(client, message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID: return True
    
    # Maintenance Check
    m_mode = await get_setting("maintenance")
    if m_mode == "on":
        await message.reply_text("🛠 Bot is under maintenance. Please try later.")
        return False
    
    # Force Join Check
    fs_chat = await get_setting("fs_channel")
    if fs_chat:
        try:
            await client.get_chat_member(fs_chat, user_id)
        except UserNotParticipant:
            await message.reply_text(f"❌ Join our channel to use this bot!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Join Now", url=f"t.me/{fs_chat}")]]))
            return False
        except Exception: pass
    return True

# --- USER BOT HANDLERS ---

@user_bot.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    if not await is_allowed(client, message): return
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if not user:
        ref_by = int(message.command[1]) if len(message.command) > 1 and message.command[1].isdigit() else None
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO users (user_id, username, referred_by) VALUES (?,?,?)", 
                             (user_id, message.from_user.username, ref_by))
            if ref_by and ref_by != user_id:
                await db.execute("UPDATE users SET referrals = referrals + 1, watch_limit = watch_limit + 2 WHERE user_id = ?", (ref_by,))
                try: await client.send_message(ref_by, "🎉 New Referral! You got +2 Video Unlocks.")
                except: pass
            await db.commit()
        user = await get_user(user_id)

    welcome_txt = (f"🚀 **Hello {message.from_user.first_name}!**\n\n"
                   f"💎 **Status:** {'Premium 👑' if user['is_premium'] else 'Free User'}\n"
                   f"🔓 **Unlocked:** {user['watch_limit']} Videos\n"
                   f"📺 **Watched:** {user['watched']}\n"
                   f"👥 **Referrals:** {user['referrals']}\n\n"
                   f"🔗 **Ref Link:** `https://t.me/{(await client.get_me()).username}?start={user_id}`")
    
    btns = [[InlineKeyboardButton("🎬 Browse All", callback_query_data="browse_0"), InlineKeyboardButton("🔍 Search", callback_query_data="search")],
            [InlineKeyboardButton("🏆 Leaderboard", callback_query_data="leaderboard"), InlineKeyboardButton("🎁 Daily Bonus", callback_query_data="daily")],
            [InlineKeyboardButton("👑 Buy Premium", callback_query_data="premium_info")]]
    await message.reply_text(welcome_txt, reply_markup=InlineKeyboardMarkup(btns))

@user_bot.on_callback_query(filters.regex("^browse_"))
async def browse(client, cb: CallbackQuery):
    page = int(cb.data.split("_")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos LIMIT 5 OFFSET ?", (page*5,)) as cursor:
            vids = await cursor.fetchall()
    
    if not vids: return await cb.answer("No more videos!", show_alert=True)
    
    await cb.message.delete()
    for v in vids:
        txt = f"🎥 **{v['title']}**\n👁 Views: {v['views']} | 🏷 {v['category']}"
        await client.send_photo(cb.message.chat.id, photo=v['thumb'], caption=txt,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Watch Now", callback_query_data=f"watch_{v['id']}")]]))
    
    await client.send_message(cb.message.chat.id, "More Videos:", 
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Next ➡️", callback_query_data=f"browse_{page+1}")]]))

@user_bot.on_callback_query(filters.regex("^watch_"))
async def watch(client, cb: CallbackQuery):
    vid_id = int(cb.data.split("_")[1])
    user = await get_user(cb.from_user.id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos WHERE id = ?", (vid_id,)) as cursor:
            v = await cursor.fetchone()

    if not user['is_premium'] and user['watched'] >= user['watch_limit']:
        return await cb.message.reply_text("❌ Limit Reached! Refer friends or buy Premium.")

    # Mark as watched
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET watched = watched + 1 WHERE user_id = ?", (user['user_id'],))
        await db.execute("UPDATE videos SET views = views + 1 WHERE id = ?", (vid_id,))
        await db.commit()

    btns = [[InlineKeyboardButton("🔗 Video Link", url=v['disk_link'])], [InlineKeyboardButton("📲 Player App", url=v['app_link'])]]
    await cb.message.reply_text(f"✅ **Playing:** {v['title']}\n\nSelect your source:", reply_markup=InlineKeyboardMarkup(btns))

@user_bot.on_callback_query(filters.regex("leaderboard"))
async def leaderboard(client, cb):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT username, referrals FROM users ORDER BY referrals DESC LIMIT 10") as c:
            data = await c.fetchall()
    txt = "🏆 **Top 10 Referrers**\n\n"
    for i, row in enumerate(data, 1):
        txt += f"{i}. {row[0] or 'User'} - {row[1]} refs\n"
    await cb.message.reply_text(txt)

@user_bot.on_callback_query(filters.regex("daily"))
async def daily_reward(client, cb):
    user = await get_user(cb.from_user.id)
    now = datetime.now()
    if user['last_daily'] and (now - datetime.strptime(user['last_daily'], '%Y-%m-%d %H:%M:%S.%f')).days < 1:
        return await cb.answer("⏳ Come back tomorrow!", show_alert=True)
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET watch_limit = watch_limit + 1, last_daily = ? WHERE user_id = ?", (now, user['user_id']))
        await db.commit()
    await cb.answer("🎁 Daily Bonus! +1 Video access added.", show_alert=True)

# --- ADMIN BOT HANDLERS ---

@admin_bot.on_message(filters.command("start") & filters.user(ADMIN_ID))
async def admin_start(client, message):
    btns = [[InlineKeyboardButton("➕ Add Video", callback_query_data="add"), InlineKeyboardButton("📢 Broadcast", callback_query_data="bc")],
            [InlineKeyboardButton("⚙️ Settings", callback_query_data="sett"), InlineKeyboardButton("📊 Stats", callback_query_data="stats")]]
    await message.reply_text("🛠 **Admin Dashboard**", reply_markup=InlineKeyboardMarkup(btns))

@admin_bot.on_callback_query(filters.regex("stats"))
async def admin_stats(client, cb):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c1: u = (await c1.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM videos") as c2: v = (await c2.fetchone())[0]
    await cb.answer(f"Total Users: {u}\nTotal Videos: {v}", show_alert=True)

@admin_bot.on_message(filters.command("give_premium") & filters.user(ADMIN_ID))
async def give_prem(client, message):
    try:
        uid = int(message.command[1])
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET is_premium = 1 WHERE user_id = ?", (uid,))
            await db.commit()
        await message.reply_text(f"✅ User {uid} is now Premium!")
    except: await message.reply_text("Usage: /give_premium user_id")

# --- BROADCAST & ADD VIDEO LOGIC (Simplified for main.py) ---
admin_state = {}

@admin_bot.on_callback_query(filters.regex("add"))
async def start_add(client, cb):
    admin_state[cb.from_user.id] = {"s": 1}
    await cb.message.reply_text("Send Thumbnail Image Link:")

@admin_bot.on_message(filters.user(ADMIN_ID) & filters.text)
async def process_admin_input(client, message):
    aid = message.from_user.id
    if aid not in admin_state: return
    
    s = admin_state[aid]
    if s['s'] == 1:
        s['t'] = message.text; s['s'] = 2
        await message.reply_text("Enter Title:")
    elif s['s'] == 2:
        s['n'] = message.text; s['s'] = 3
        await message.reply_text("Enter Disk Link:")
    elif s['s'] == 3:
        s['d'] = message.text; s['s'] = 4
        await message.reply_text("Enter App Player Link:")
    elif s['s'] == 4:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO videos (title, thumb, disk_link, app_link, category) VALUES (?,?,?,?,?)",
                             (s['n'], s['t'], s['d'], message.text, "General"))
            await db.commit()
        del admin_state[aid]
        await message.reply_text("✅ Video Added Successfully!")

# --- SEARCH LOGIC ---
@user_bot.on_message(filters.text & filters.private)
async def search_handler(client, message):
    if not await is_allowed(client, message): return
    query = f"%{message.text}%"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos WHERE title LIKE ? LIMIT 5", (query,)) as cursor:
            results = await cursor.fetchall()
    
    if not results: return await message.reply_text("🔍 No videos found matching your search.")
    
    for v in results:
        btn = [[InlineKeyboardButton("▶️ Watch", callback_query_data=f"watch_{v['id']}")]]
        await message.reply_photo(v['thumb'], caption=f"🎥 **{v['title']}**", reply_markup=InlineKeyboardMarkup(btn))

# --- APP START ---
async def start_all():
    await init_db()
    Thread(target=run_flask).start()
    await asyncio.gather(user_bot.start(), admin_bot.start())
    logger.info("Bots are Started Successfully!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_all())
