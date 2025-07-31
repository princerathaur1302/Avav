import os
import time
import logging
import json
import asyncio
from PIL import Image
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from oauth2client.client import OAuth2WebServerFlow, FlowExchangeError
from oauth2client.file import Storage
import time
from yt_dlp import YoutubeDL
from urllib.parse import quote
import subprocess
import requests
import re


def safe_delete(file_path, retries=5, delay=1):
    for _ in range(retries):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                break
        except PermissionError:
            time.sleep(delay)


import subprocess
import os
import shutil

def fix_metadata_duration(file_path):
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        return

    temp_path = file_path.replace(".mp4", "_fixed.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-i", file_path,
        "-c:v", "copy",
        "-c:a", "copy",
        "-movflags", "+faststart",
        temp_path
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if os.path.exists(temp_path):
        os.remove(file_path)
        shutil.move(temp_path, file_path)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============ CONFIGURATION ============
API_ID = 20214595
API_HASH = "4763f66ce1a18c2dd491a5048891926c"
BOT_TOKEN = "8235342718:AAH3u7K8G9Rzz1GwU1eJCWVzeUMAhDg2rwI"
ADMIN_ID = 7281824001
CREDIT = " @contact_262524_bot "


CLIENT_SECRET_FILE = 'client_secret.json'
USERS_FILE = 'allowed_users.json'
USER_SETTINGS_FILE = 'user_settings.json'
THUMBNAILS_DIR = 'thumbnails'
os.makedirs(THUMBNAILS_DIR, exist_ok=True)

USER_TOKENS_DIR = 'tokens'
USER_SECRETS_DIR = 'secrets'
os.makedirs(USER_TOKENS_DIR, exist_ok=True)
os.makedirs(USER_SECRETS_DIR, exist_ok=True)


user_data = {}
allowed_users = {}
user_settings = {}
pending_auth = {}
token_waiters = {}
batch_message_tracker = {}
app = Client("youtube_upload_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# ============ DRM ============

def get_ffmpeg_path():
   return "ffmpeg"

def get_video_duration(file_path):
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return int(float(result.stdout))
    except:
        return 0
    
def clean_spoilers(text):
    return text.replace("||", "_")  # Telegram spoiler fix

def extract_thumbnail(video_path, output_thumb, time_in_sec=1):
    cmd = [
        "ffmpeg",
        "-ss", str(time_in_sec),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        output_thumb
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_thumb if os.path.exists(output_thumb) else None



def wait_for_token(chat_id):
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    token_waiters[chat_id] = future
    return future

async def track_message(msg):
    chat_id = msg.chat.id
    batch_message_tracker.setdefault(chat_id, []).append(msg.id)

async def batch_delete_tracked_messages(client, chat_id):
    if chat_id in batch_message_tracker:
        for msg_id in batch_message_tracker[chat_id]:
            try:
                await client.delete_messages(chat_id, msg_id)
            except:
                pass
        batch_message_tracker[chat_id] = []

async def download_file_with_progress(url, dest_path, msg, chat_id):
    r = requests.get(url, stream=True)
    total = int(r.headers.get('content-length', 0))
    downloaded = 0
    start_time = time.time()
    last_update = 0

    with open(dest_path, 'wb') as f:
        for chunk in r.iter_content(1024 * 1024):
            f.write(chunk)
            downloaded += len(chunk)

            now = time.time()
            if now - last_update >= 3:
                percent = (downloaded / total * 100) if total else 0
                elapsed = now - start_time if now > start_time else 1
                speed = downloaded / elapsed / (1024 * 1024)

                await msg.edit(
                    f"📥 Downloading...\n"
                    f"├─ Progress: {percent:.2f}%\n"
                    f"├─ Speed: {speed:.2f} MB/s\n"
                    f"└─ {downloaded // (1024 * 1024)}MB / {total // (1024 * 1024)}MB"
                )
                last_update = now

    return dest_path


async def upload_file_with_progress(client, chat_id, file_path, caption, is_video):
    sent_msg = await client.send_message(chat_id, "📤 Uploading...")
    await track_message(sent_msg)

    file_size = os.path.getsize(file_path)
    uploaded = 0
    start = time.time()
    last = 0

    async def progress(current, total):
        nonlocal uploaded, last
        uploaded = current
        now = time.time()
        if now - last >= 3:
            percent = uploaded * 100 / total
            speed = uploaded / (now - start) / (1024 * 1024)
            try:
                await sent_msg.edit_text(
                    f"📤 Uploading...\n"
                    f"├ Progress: {percent:.2f}%\n"
                    f"├ Speed: {speed:.2f} MB/s\n"
                    f"└ {uploaded//(1024*1024)}MB / {file_size//(1024*1024)}MB"
                )
            except:
                pass
            last = now

    if is_video:
        duration = get_video_duration(file_path)
        await client.send_video(
            chat_id,
            file_path,
            caption=caption,
            progress=progress,
            supports_streaming=True,
            duration=duration
        )
    else:
        await client.send_document(chat_id, file_path, caption=caption, progress=progress)

    await batch_delete_tracked_messages(client, chat_id)
    if os.path.exists(file_path):
        os.remove(file_path)

# ============ HELPERS ============
def is_user_allowed(user_id):
    return user_id == ADMIN_ID or user_id in allowed_users["users"]

def has_configured_settings(user_id):
    user_id = str(user_id)
    return user_id in user_settings and all(k in user_settings[user_id] for k in ['title', 'thumbnail'])

def get_default_thumbnail_path(user_id):
    return os.path.join(THUMBNAILS_DIR, f"{user_id}.jpg")


async def track_msg(user_id, msg):
    if user_id in user_data:
        user_data[user_id].setdefault("del_msgs", []).append(msg.id)

async def delete_tracked_messages(client, chat_id, user_id):
    if user_id in user_data and "del_msgs" in user_data[user_id]:
        for msg_id in user_data[user_id]["del_msgs"]:
            try:
                await client.delete_messages(chat_id, msg_id)
            except:
                pass
        user_data[user_id]["del_msgs"] = []


def get_video_duration(file_path):
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return int(float(result.stdout))
    except:
        return 0


# ============ DOWNLOAD FUNCTION ============
async def download_large_file(client, message, file_path):
    user_id = message.from_user.id
    file_size = message.video.file_size
    downloaded = 0
    chunk_size = 1024 * 1024
    start_time = time.time()
    last_update_time = 0

    status_msg = await message.reply("📥 Downloading...")
    await track_msg(user_id, status_msg)


    with open(file_path, 'wb') as f:
        async for chunk in client.stream_media(message, chunk_size):
            if user_data.get(user_id, {}).get("cancelled"):
                await status_msg.edit_text("❌ Download cancelled.")
                return None
            f.write(chunk)
            downloaded += len(chunk)

            current_time = time.time()
            if current_time - last_update_time >= 4:
                progress = (downloaded / file_size) * 100
                elapsed_time = current_time - start_time
                speed = downloaded / (elapsed_time * 1024 * 1024)
                await status_msg.edit_text(
                    f"📥 Downloading...\n"
                    f"├ Progress: {progress:.1f}%\n"
                    f"├ Speed: {speed:.2f} MB/s\n"
                    f"└ {downloaded//(1024*1024)}MB/{file_size//(1024*1024)}MB" )
                last_update_time = current_time

    return status_msg



  # ===================== COMMAND HANDLERS =====================


@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    user_id = message.from_user.id

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📩 Contact Admin", url="https://t.me/contact_262524_bot")]
    ])

    if not is_user_allowed(user_id):
        await message.reply(
            "❌ You are not authorized to use this bot!",
            reply_markup=keyboard
        )
        return

    await message.reply(
        "👋 Welcome to YouTube Uploader Bot!\n\nUse /help to see how to use it",
        reply_markup=keyboard
    )

@app.on_message(filters.command("batch"))
async def batch_request(client, message):
    if not is_user_allowed(message.from_user.id):
        await message.reply("❌ You are not authorized to use this bot!")
        return
        
    msg = await message.reply("📄 Please send your .txt file now.")
    await track_message(msg)
    await track_message(message)



@app.on_message(filters.command("help"))
async def help_cmd(c, m):
    await m.reply(
      f"╭━━━━━━━✦✧✦━━━━━━━╮\n💥 𝘽𝙊𝙏𝙎 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦\n╰━━━━━━━✦✧✦━━━━━━━╯\n ▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n 📌 𝗠𝗮𝗶𝗻 𝗙𝗲𝗮𝘁𝘂𝗿𝗲𝘀:\n➥ /start – Bot Status Check\n➥ /video – Send a video to upload \n➥ /batch – Upload PW Batch\n➥ /settings – Set Your Details \n➥ /auth – Verify Your YT Channel\n➥ /help – See Command Details\n➥ /cancel – Stop Uploading\n▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n👤 𝐔𝐬𝐞𝐫 𝐀𝐮𝐭𝐡𝐞𝐧𝐭𝐢𝐜𝐚𝐭𝐢𝐨𝐧: **(OWNER)**\n➥ /adduser xxxx – Add User ID\n➥ /removeuser xxxx – Remove User ID\n➥ /userlist – Total User List\n▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰ \n🤖 𝔹𝕠𝕥 𝔽𝕖𝕒𝕥𝕦𝕣𝕖: \n🎥 Send video (up to 2GB)\n📝 Custom Title \n📷 Custom Thumbnail \n📤 Video uploads to YouTube (unlisted) \n ▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰\n 💡 𝗡𝗼𝘁𝗲:\n • Please Support Devloper\n╭──────────⊰◆⊱──────────╮\n  ➠ 𝐌𝐚𝐝𝐞 𝐁𝐲 : {CREDIT} 💻\n╰──────────⊰◆⊱──────────╯\n"
           )


# ===================== ADMIN COMMAND HANDLERS =====================
@app.on_message(filters.command("adduser"))
async def add_user_command(client, message: Message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        await message.reply("❌ Only admin can add users!")
        return
    
    try:
        if len(message.command) < 2:
            await message.reply("Usage: /adduser [user_id]")
            return
            
        new_user_id = int(message.command[1])
        if new_user_id in allowed_users["users"]:
            await message.reply("ℹ️ User already exists in the list")
        else:
            allowed_users["users"].append(new_user_id)
            save_users()
            await message.reply(f"✅ User {new_user_id} added successfully!")
    except (IndexError, ValueError):
        await message.reply("❌ Invalid format. Usage: /adduser [user_id]")

@app.on_message(filters.command("removeuser"))
async def remove_user_command(client, message: Message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        await message.reply("❌ Only admin can remove users!")
        return
    
    try:
        if len(message.command) < 2:
            await message.reply("Usage: /removeuser [user_id]")
            return
            
        remove_user_id = int(message.command[1])
        if remove_user_id in allowed_users["users"]:
            allowed_users["users"].remove(remove_user_id)
            save_users()
            await message.reply(f"✅ User {remove_user_id} removed successfully!")
        else:
            await message.reply("❌ User not found in the list")
    except (IndexError, ValueError):
        await message.reply("❌ Invalid format. Usage: /removeuser [user_id]")

@app.on_message(filters.command("userlist"))
async def user_list_command(client, message: Message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        await message.reply("❌ Only admin can view user list!")
        return
    
    if not allowed_users["users"]:
        await message.reply("ℹ️ No users added yet")
    else:
        users_list = "\n".join([f"👤 {user_id}" for user_id in allowed_users["users"]])
        await message.reply(f"📝 Authorized Users:\n{users_list}")


# ============ DRM ============




@app.on_message(filters.document & filters.private)
async def handle_txt(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_user_allowed(user_id):
        return

    await track_message(message)
    batch_name = os.path.splitext(message.document.file_name)[0]
    notice = await message.reply("📥 Processing file...")
    await track_message(notice)

    file_path = await message.download()
    await track_message(message)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        token_required = any("childId=" in l for l in lines)
        token = None
        if token_required:
            prompt = await client.send_message(chat_id, f"🔐 Token required for this batch.\nSend token now.")
            await track_message(prompt)
            token = await wait_for_token(chat_id)

        for line in lines:
            if ":https://" not in line:
                continue

            title, url = line.split(":https://", 1)
            title = title.strip()
            url = "https://" + url.strip()

            if url.endswith(".pdf"):
                caption = (
                    f"📄 <b>File Title :</b> {title}\n\n"
                    f"<pre><code>**📦 Batch Name :** {batch_name}</code></pre>\n"
                    f"<b>Contact (Admin) ➤</b> {CREDIT} \n\n"
                    f"<b>Join Now...🔻</b> \n"
                    f"https://t.me/addlist/Yfez5bB2FiljMzE1\n"
                    f"https://youtube.com/@LocalBoyPrince"
                )
                msg = await message.reply(f"📄 Downloading PDF: {title}")
                await track_message(msg)
                try:

                    safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)  # Yeh unsafe characters ko "_"" me badal dega
                    pdf_name = f"{safe_title.replace(' ', '_')}.pdf"  # Final safe filename
                    await download_file_with_progress(url, pdf_name, msg, chat_id)
                    await upload_file_with_progress(client, chat_id, pdf_name, caption, is_video=False)
                except Exception as e:
                    await msg.edit(f"❌ PDF failed: {str(e)}")
                continue

            if "childId=" in url and token:
                encoded_url = quote(url, safe=":/&?=")
                url = f"https://anonymouspwplayerr-f996115ea61a.herokuapp.com/pw?url={encoded_url}&token={token}"

            msg = await message.reply(f"🎞 Downloading video: {title}")
            await track_message(msg)

            try:
                filename = f"{title.replace(' ', '_')}.mp4"



                ydl_opts = {
    "format": "bestvideo+bestaudio/best",
    "outtmpl": "downloads/%(title)s.%(ext)s",
    "noplaylist": True,
    "concurrent_fragment_downloads": 10,
    "retries": 10,
    "fragment_retries": 5,
    "throttled_rate": None,
    "http_chunk_size": 1048576,  # 1MB
    "nopart": True,              # don't create .part files
    "continuedl": True           # resume if interrupted
}




                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    path = ydl.prepare_filename(info)

                # Prepare caption
                safe_title = clean_spoilers(title)
                safe_batch = clean_spoilers(batch_name)

                caption = (
                    f"📄 <b>File Title :</b> {safe_title}\n\n"
                    f"<b>YOUTUBE Link...</b>🔻\n"
                    f"Uploading...\n\n"
                    f"<pre><code>**📦 Batch Name :** {safe_batch}</code></pre>\n"
                    f"<b>Contact (Admin) ➤</b> {CREDIT} \n\n"
                    f"<b>Join Now...🔻</b>\n"
                    f"https://t.me/addlist/Yfez5bB2FiljMzE1\n"
                    f"https://youtube.com/@LocalBoyPrince"
                )

                # Upload to Telegram first
                fix_metadata_duration(path)
                duration = get_video_duration(path)
                thumb_path = path.replace(".mp4", "_thumb.jpg")
                extract_thumbnail(path, thumb_path)

                sent = await client.send_video(
                    chat_id,
                    path,
                    caption=caption,
                    supports_streaming=True,
                    duration=duration,
                    thumb=thumb_path if os.path.exists(thumb_path) else None
                )

                if os.path.exists(thumb_path):
                    os.remove(thumb_path)


    except Exception as e:
        await notice.edit(f"❌ Error: {str(e)}")

# ===================== MESSAGE HANDLERS =====================
@app.on_message(filters.text & ~filters.command(["start", "help", "video", "settings", "cancel", "auth"]))
async def handle_text(client, message: Message):
    user_id = message.from_user.id
    
            

    if message.chat.id in token_waiters:
        token_waiters[message.chat.id].set_result(message.text)
        del token_waiters[message.chat.id]
    await track_message(message)



import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_keepalive():
    server = HTTPServer(('0.0.0.0', 10000), KeepAliveHandler)
    server.serve_forever()

threading.Thread(target=run_keepalive).start()

# ===================== MAIN =====================
print("Bot is running...")
app.run()
 
