import os
import asyncio
import logging
import aiosqlite
import requests
from datetime import datetime
from flask import Flask
from threading import Thread
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BeastBot")

# --- CONFIGURATION ---
# Environment variables se data lega
API_ID = int(os.getenv("API_ID", "34353387"))
API_HASH = os.getenv("API_HASH", "79c65fb48e0eff802aededcef0c19d26")
USER_BOT_TOKEN = os.getenv("USER_BOT_TOKEN")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Database path (Render Disk friendly)
DB_PATH = "/data/beast_streaming.db" if os.path.exists("/data") else "beast_streaming.db"
PORT = int(os.getenv("PORT", "8080"))

# --- FLASK SERVER (For Render Port Binding) ---
app = Flask(__name__)
@app.route('/')
def home(): return "SYSTEM IS ONLINE 🚀"

def run_web():
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
            disk_link TEXT, app_link TEXT, category TEXT, views INTEGER DEFAULT 0
        )""")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        defaults = [('admin_user', '@Admin'), ('fs_channel', ''), ('shortlink_api', ''), ('shortlink_url', '')]
        for k, v in defaults:
            await db.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (k, v))
        await db.commit()

# --- BOT CLIENTS ---
user_bot = Client("user_bot", api_id=API_ID, api_hash=API_HASH, bot_token=USER_BOT_TOKEN)
admin_bot = Client("admin_bot", api_id=API_ID, api_hash=API_HASH, bot_token=ADMIN_BOT_TOKEN)

# --- DATABASE HELPERS ---
async def get_user(uid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (uid,)) as c:
            return await c.fetchone()

async def get_set(k):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (k,)) as c:
            r = await c.fetchone()
            return r[0] if r else ""

# --- USER BOT LOGIC ---
@user_bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    uid = message.from_user.id
    user = await get_user(uid)
    
    if not user:
        ref_by = int(message.command[1]) if len(message.command) > 1 and message.command[1].isdigit() else None
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO users (user_id, username, referred_by) VALUES (?,?,?)", (uid, message.from_user.username, ref_by))
            if ref_by and ref_by != uid:
                await db.execute("UPDATE users SET referrals = referrals + 1, watch_limit = watch_limit + 2 WHERE user_id = ?", (ref_by,))
                try: await client.send_message(ref_by, "🎉 Referral Success! +2 Videos Unlocked.")
                except: pass
            await db.commit()
        user = await get_user(uid)

    fs = await get_set("fs_channel")
    if fs:
        try: await client.get_chat_member(fs, uid)
        except UserNotParticipant:
            return await message.reply_text(f"❌ Join our channel to use this bot!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Join Channel", url=f"t.me/{fs}")]]))

    text = (f"🚀 **STREAMING DASHBOARD**\n\n⭐ Level: {user['level']} | XP: {user['xp']}\n"
            f"🔓 Limit: {user['watch_limit']} Videos\n"
            f"👥 Referrals: {user['referrals']}\n"
            f"👑 Premium: {'✅' if user['is_premium'] else '❌'}\n\n"
            f"🔗 Ref Link: `https://t.me/{(await client.get_me()).username}?start={uid}`")
    
    btns = [[InlineKeyboardButton("🎬 Browse All", callback_query_data="browse_0")],
            [InlineKeyboardButton("🏆 Leaderboard", callback_query_data="leader"), InlineKeyboardButton("🔍 Search", callback_query_data="srch")],
            [InlineKeyboardButton("👑 Buy Premium", callback_query_data="buy")]]
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(btns))

@user_bot.on_callback_query(filters.regex("^browse_"))
async def browse_vids(client, cb: CallbackQuery):
    page = int(cb.data.split("_")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos LIMIT 5 OFFSET ?", (page*5,)) as cursor: 
            vids = await cursor.fetchall()
    
    if not vids: return await cb.answer("No more videos!", show_alert=True)
    await cb.message.delete()
    for v in vids:
        await client.send_photo(cb.message.chat.id, photo=v['thumb'], caption=f"🎥 **{v['title']}**\n👁 Views: {v['views']}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Watch Now", callback_query_data=f"watch_{v['id']}")]]))
    await client.send_message(cb.message.chat.id, "More Videos:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Next Page ➡️", callback_query_data=f"browse_{page+1}")]]))

@user_bot.on_callback_query(filters.regex("^watch_"))
async def play_vid(client, cb: CallbackQuery):
    vid_id = int(cb.data.split("_")[1])
    user = await get_user(cb.from_user.id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos WHERE id = ?", (vid_id,)) as c: 
            v = await c.fetchone()

    if not user['is_premium'] and user['watched'] >= user['watch_limit']:
        return await cb.answer("⚠️ Limit Over! Refer friends to unlock more.", show_alert=True)

    async with aiosqlite.connect(DB_PATH) as db:
        new_xp = user['xp'] + 1
        new_lvl = user['level'] + (1 if new_xp % 10 == 0 else 0)
        await db.execute("UPDATE users SET watched = watched + 1, xp = ?, level = ? WHERE user_id = ?", (new_xp, new_lvl, user['user_id']))
        await db.execute("UPDATE videos SET views = views + 1 WHERE id = ?", (vid_id,))
        await db.commit()

    btns = [[InlineKeyboardButton("🔗 Watch Video", url=v['disk_link'])], [InlineKeyboardButton("📲 Player App", url=v['app_link'])]]
    await cb.message.reply_text(f"🎬 **{v['title']}**\n\nEnjoy your stream!", reply_markup=InlineKeyboardMarkup(btns))

# --- ADMIN PANEL ---
ad_states = {}

@admin_bot.on_message(filters.command("admin") & filters.user(ADMIN_ID))
async def admin_menu(client, message):
    btns = [[InlineKeyboardButton("➕ Add Video", callback_query_data="add_v"), InlineKeyboardButton("📊 Stats", callback_query_data="stats")],
            [InlineKeyboardButton("⚙️ Settings", callback_query_data="sett")]]
    await message.reply_text("👑 **Admin Master Panel**", reply_markup=InlineKeyboardMarkup(btns))

@admin_bot.on_callback_query(filters.regex("add_v") & filters.user(ADMIN_ID))
async def add_vid_step1(client, cb: CallbackQuery):
    ad_states[cb.from_user.id] = {"step": 1}
    await cb.message.reply_text("Step 1: Send Thumbnail Image URL")

@admin_bot.on_message(filters.user(ADMIN_ID) & filters.text)
async def admin_inputs(client, message):
    aid = message.from_user.id
    if aid not in ad_states: return
    state = ad_states[aid]
    
    if state['step'] == 1:
        state['thumb'] = message.text; state['step'] = 2
        await message.reply_text("Step 2: Enter Video Title")
    elif state['step'] == 2:
        state['title'] = message.text; state['step'] = 3
        await message.reply_text("Step 3: Enter Disk Link")
    elif state['step'] == 3:
        state['disk'] = message.text; state['step'] = 4
        await message.reply_text("Step 4: Enter App Player Link")
    elif state['step'] == 4:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO videos (title, thumb, disk_link, app_link) VALUES (?,?,?,?)", (state['title'], state['thumb'], state['disk'], message.text))
            await db.commit()
        del ad_states[aid]
        await message.reply_text("✅ Video Added Successfully!")

# --- MAIN RUNNER ---
async def start_all():
    await init_db()
    # Flask ko start karna Render ke liye zaruri hai
    Thread(target=run_web, daemon=True).start()
    
    await user_bot.start()
    await admin_bot.start()
    logger.info("SYSTEM STARTED SUCCESSFULLY 🚀")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(start_all())
    except (KeyboardInterrupt, SystemExit):
        pass
