import os, asyncio, logging, aiosqlite, requests
from datetime import datetime
from flask import Flask
from threading import Thread
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import UserNotParticipant, FloodWait

# --- CONFIGURATION ---
API_ID = int(os.getenv("API_ID", "34353387"))
API_HASH = os.getenv("API_HASH", "79c65fb48e0eff802aededcef0c19d26")
USER_BOT_TOKEN = os.getenv("USER_BOT_TOKEN")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = "/data/beast_stream.db" if os.path.exists("/data") else "beast_stream.db"

# --- LOGGING & WEB SERVER ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BeastBot")
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
            xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1, last_active TIMESTAMP
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, thumb TEXT, 
            disk_link TEXT, app_link TEXT, category TEXT, views INTEGER DEFAULT 0, is_premium BOOLEAN DEFAULT 0
        )""")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        # Default Settings
        defaults = [('admin_user', '@Admin'), ('fs_channel', ''), ('m_mode', 'off'), ('ref_reward', '2')]
        for k, v in defaults:
            await db.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (k, v))
        await db.commit()

# --- BOTS INITIALIZATION ---
user_bot = Client("user_bot", api_id=API_ID, api_hash=API_HASH, bot_token=USER_BOT_TOKEN)
admin_bot = Client("admin_bot", api_id=API_ID, api_hash=API_HASH, bot_token=ADMIN_BOT_TOKEN)

# --- DATABASE HELPERS ---
async def get_user(uid):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (uid,)) as c: return await c.fetchone()

async def get_set(k):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (k,)) as c:
            r = await c.fetchone()
            return r[0] if r else ""

# --- USER BOT: CORE FEATURES ---

@user_bot.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    uid = message.from_user.id
    user = await get_user(uid)
    
    # Referral Check
    if not user:
        ref_by = int(message.command[1]) if len(message.command) > 1 and message.command[1].isdigit() else None
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO users (user_id, username, referred_by, last_active) VALUES (?,?,?,?)", 
                             (uid, message.from_user.username, ref_by, datetime.now()))
            if ref_by and ref_by != uid:
                reward = int(await get_set("ref_reward"))
                await db.execute(f"UPDATE users SET referrals = referrals + 1, watch_limit = watch_limit + {reward} WHERE user_id = ?", (ref_by,))
                try: await client.send_message(ref_by, f"🔥 Success! Someone joined. You got +{reward} Limit.")
                except: pass
            await db.commit()
        user = await get_user(uid)

    # Force Join Check
    fs = await get_set("fs_channel")
    if fs:
        try:
            await client.get_chat_member(fs, uid)
        except UserNotParticipant:
            return await message.reply_text(f"🚀 Join our channel to use this bot!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Join Channel", url=f"t.me/{fs}")]]))

    # XP Dashboard
    text = (f"👤 **DASHBOARD**\n━━━━━━━━━━\n"
            f"⭐ **Level:** {user['level']} | **XP:** {user['xp']}\n"
            f"🔓 **Access:** {user['watch_limit']} Videos\n"
            f"👑 **Premium:** {'✅' if user['is_premium'] else '❌'}\n"
            f"👥 **Referrals:** {user['referrals']}\n━━━━━━━━━━\n"
            f"🔗 `https://t.me/{(await client.get_me()).username}?start={uid}`")
    
    btns = [[InlineKeyboardButton("🎬 Browse Videos", callback_query_data="browse_0"), InlineKeyboardButton("🔍 Search", callback_query_data="search_ui")],
            [InlineKeyboardButton("🏆 Leaderboard", callback_query_data="leaderboard"), InlineKeyboardButton("👑 Get Premium", callback_query_data="buy_prem")]]
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(btns))

@user_bot.on_callback_query(filters.regex("^browse_"))
async def browse(client, cb: CallbackQuery):
    page = int(cb.data.split("_")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos LIMIT 5 OFFSET ?", (page*5,)) as c: vids = await c.fetchall()
    
    if not vids: return await cb.answer("No more videos!", show_alert=True)
    await cb.message.delete()
    for v in vids:
        await client.send_photo(cb.message.chat.id, photo=v['thumb'], 
            caption=f"🎥 **{v['title']}**\n👁 Views: {v['views']}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("▶️ Watch", callback_query_data=f"watch_{v['id']}")]]))
    await client.send_message(cb.message.chat.id, "Navigate:", 
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Next ➡️", callback_query_data=f"browse_{page+1}")]]))

@user_bot.on_callback_query(filters.regex("^watch_"))
async def watch_vid(client, cb: CallbackQuery):
    vid_id = int(cb.data.split("_")[1])
    user = await get_user(cb.from_user.id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM videos WHERE id = ?", (vid_id,)) as c: v = await c.fetchone()

    if not user['is_premium'] and user['watched'] >= user['watch_limit']:
        return await cb.message.reply_text("❌ Limit Reached! Refer friends or buy Premium.")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET watched = watched+1, xp = xp+1 WHERE user_id = ?", (user['user_id'],))
        await db.execute("UPDATE videos SET views = views+1 WHERE id = ?", (vid_id,))
        await db.commit()

    btns = [[InlineKeyboardButton("🔗 Watch Video", url=v['disk_link'])], [InlineKeyboardButton("📲 Player App", url=v['app_link'])]]
    await cb.message.reply_text(f"✅ Ready: {v['title']}\n🌟 +1 XP Gained!", reply_markup=InlineKeyboardMarkup(btns))

@user_bot.on_callback_query(filters.regex("leaderboard"))
async def top_ref(client, cb):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT username, referrals FROM users ORDER BY referrals DESC LIMIT 10") as c:
            rows = await c.fetchall()
    txt = "🏆 **Leaderboard**\n\n"
    for i, r in enumerate(rows, 1): txt += f"{i}. {r[0]} - {r[1]} refs\n"
    await cb.message.reply_text(txt)

# --- ADMIN BOT: FULL CONTROL ---

@admin_bot.on_message(filters.command("start") & filters.user(ADMIN_ID))
async def admin_start(client, message):
    btns = [[InlineKeyboardButton("📊 Stats", callback_query_data="st"), InlineKeyboardButton("➕ Add Video", callback_query_data="add_v")],
            [InlineKeyboardButton("⚙️ Settings", callback_query_data="sets"), InlineKeyboardButton("📢 Broadcast", callback_query_data="bc")]]
    await message.reply_text("👑 **Admin Panel**", reply_markup=InlineKeyboardMarkup(btns))

@admin_bot.on_callback_query(filters.regex("st"))
async def admin_st(client, cb):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c1: u = (await c1.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM videos") as c2: v = (await c2.fetchone())[0]
    await cb.answer(f"Users: {u}\nVideos: {v}", show_alert=True)

# Video Adding Logic
ad_data = {}
@admin_bot.on_callback_query(filters.regex("add_v"))
async def start_add(client, cb):
    ad_data[cb.from_user.id] = {"s": 1}
    await cb.message.reply_text("Send Thumbnail URL:")

@admin_bot.on_message(filters.user(ADMIN_ID) & filters.text)
async def admin_inputs(client, message):
    aid = message.from_user.id
    if aid not in ad_data: return
    s = ad_data[aid]
    if s['s'] == 1:
        s['thumb'] = message.text; s['s'] = 2
        await message.reply_text("Enter Video Title:")
    elif s['s'] == 2:
        s['title'] = message.text; s['s'] = 3
        await message.reply_text("Enter Disk Link:")
    elif s['s'] == 3:
        s['disk'] = message.text; s['s'] = 4
        await message.reply_text("Enter App Link:")
    elif s['s'] == 4:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO videos (title, thumb, disk_link, app_link) VALUES (?,?,?,?)",
                             (s['title'], s['thumb'], s['disk'], message.text))
            await db.commit()
        del ad_data[aid]
        await message.reply_text("✅ Added Successfully!")

# Settings & Premium
@admin_bot.on_message(filters.command("give_premium") & filters.user(ADMIN_ID))
async def give_p(client, message):
    uid = int(message.command[1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_premium = 1 WHERE user_id = ?", (uid,))
        await db.commit()
    await message.reply_text(f"✅ User {uid} is now Premium.")

# --- MAIN RUNNER ---
async def main():
    await init_db()
    Thread(target=run_web, daemon=True).start()
    await user_bot.start()
    await admin_bot.start()
    logger.info("SYSTEM READY 🚀")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except: pass
