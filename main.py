from pyrogram import Client, filters
import requests
import os
import asyncio
import time
from yt_dlp import YoutubeDL
from urllib.parse import quote
import subprocess
import re
import traceback

API_ID = 20214595
API_HASH = "4763f66ce1a18c2dd491a5048891926c"
BOT_TOKEN = "8235342718:AAH3u7K8G9Rzz1GwU1eJCWVzeUMAhDg2rwI"
CREDIT = " @contact_262524_bot "
app = Client("pdf_video_batch_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

token_waiters = {}
message_tracker = {}

def wait_for_token(chat_id):
loop = asyncio.get_event_loop()
future = loop.create_future()
token_waiters[chat_id] = future
return future

async def track_message(msg):
chat_id = msg.chat.id
message_tracker.setdefault(chat_id, []).append(msg.id)

async def delete_tracked_messages(client, chat_id):
if chat_id in message_tracker:
for msg_id in message_tracker[chat_id]:
try:
await client.delete_messages(chat_id, msg_id)
except:
pass
message_tracker[chat_id] = []

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

await delete_tracked_messages(client, chat_id)  
if os.path.exists(file_path):  
    os.remove(file_path)

@app.on_message(filters.command("start"))
async def start(client, message):
msg = await message.reply("👋 Use /batch and send a .txt file:\n<Title>:<URL>")
await track_message(msg)
await track_message(message)

@app.on_message(filters.command("batch"))
async def batch_request(client, message):
msg = await message.reply("📄 Please send your .txt file now.")
await track_message(msg)
await track_message(message)

@app.on_message(filters.document & filters.private)
async def handle_txt(client, message):
await track_message(message)
if not message.document.file_name.endswith(".txt"):
return

chat_id = message.chat.id  
batch_name = os.path.splitext(message.document.file_name)[0]  
notice = await message.reply("📥 Processing file...")  
await track_message(notice)  

file_path = await message.download()  
await track_message(message)  

def parse_line(line):  
    if ":https://" not in line:  
        return None, None  
    title, url = line.split(":https://", 1)  
    return title.strip(), "https://" + url.strip()  

async def get_token_with_timeout(chat_id, timeout=60):  
    try:  
        return await asyncio.wait_for(wait_for_token(chat_id), timeout)  
    except asyncio.TimeoutError:  
        return None  

try:  
    with open(file_path, "r", encoding="utf-8") as f:  
        lines = f.readlines()  

    token_required = any("childId=" in l for l in lines)  
    token = None  
    if token_required:  
        prompt = await client.send_message(chat_id, f"🔐 Token required for this batch.\nSend token now (within 60s).")  
        await track_message(prompt)  
        token = await get_token_with_timeout(chat_id)  
        if not token:  
            await client.send_message(chat_id, "❌ Token timeout. Try /batch again.")  
            return  

    for line in lines:  
        title, url = parse_line(line)  
        if not url:  
            continue  

        if url.endswith(".pdf"):  
            caption = (f"📄 **File Title :** {title}\n\n<pre><code>**📦 Batch Name :** {batch_name}</code></pre>\n**Contact (Admin) ➤**{CREDIT} \n\n**Join Now...🔻** \n https://t.me/addlist/Yfez5bB2FiljMzE1\n https://youtube.com/@LocalBoyPrince")  
            msg = await message.reply(f"📄 Downloading PDF: {title}")  
            await track_message(msg)  
            try:  
                pdf_name = f"{title.replace(' ', '_')}.pdf"  
                await download_file_with_progress(url, pdf_name, msg, chat_id)  
                await upload_file_with_progress(client, chat_id, pdf_name, caption, is_video=False)  
            except Exception as e:  
                await msg.edit(f"❌ PDF failed: {str(e)}")  
            continue  

        # Common function for both types  
        async def download_video(url, title):  
            msg = await message.reply(f"🎞 Downloading video: {title}")  
            await track_message(msg)  

            try:  
                download_progress = {"last_update": 0, "start": time.time()}  

                def hook(d):  
                    if d["status"] == "downloading":  
                        now = time.time()  
                        if now - download_progress["last_update"] >= 3:  
                            downloaded = d.get("downloaded_bytes", 0)  
                            total_bytes = d.get("total_bytes", 0)  
                            speed_bytes = d.get("speed", 0)  

                            percent = (downloaded / total_bytes * 100) if total_bytes else 0  
                            speed = f"{speed_bytes / (1024 * 1024):.2f} MB/s" if speed_bytes else "N/A"  
                            size = f"{downloaded // (1024*1024)}MB / {total_bytes // (1024*1024)}MB" if total_bytes else f"{downloaded // (1024*1024)}MB / ?MB"  

                            text = f"**WAIT PLEASE**\n{percent:.2f}% | {speed}"  
                            try:  
                                asyncio.create_task(msg.edit_text(text))  
                            except:  
                                pass  
                            download_progress["last_update"] = now  

                ydl_opts = {  
                    "outtmpl": f"{title.replace(' ', '_')}.%(ext)s",  
                    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",  
                    "merge_output_format": "mp4",  
                    "quiet": True,  
                    "progress_hooks": [hook],  
                    "postprocessors": [  
                        {"key": "FFmpegMetadata"},  
                        {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}  
                    ]  
                }  

                with YoutubeDL(ydl_opts) as ydl:  
                    info = ydl.extract_info(url, download=True)  
                    path = ydl.prepare_filename(info)  

                caption = (f"📄 **File Title :** {title}\n\n<pre><code>**📦 Batch Name :** {batch_name}</code></pre>\n**Contact (Admin) ➤**{CREDIT} \n\n**Join Now...🔻** \n https://t.me/addlist/Yfez5bB2FiljMzE1\n https://youtube.com/@LocalBoyPrince")  
                await upload_file_with_progress(client, chat_id, path, caption, is_video=True)  

            except Exception as e:  
                await msg.edit(f"❌ Video Error:\n{str(e)}\n\nURL: {url}")  

        # Special handling for childId  
        if "childId=" in url and token:  
            from urllib.parse import quote  
            encoded_url = quote(url, safe=":/&?=")  
            new_url = f"https://anonymousrajputplayer-9ab2f2730a02.herokuapp.com/pw?url={encoded_url}&token={token}"  
            await download_video(new_url, title)  
        else:  
            await download_video(url, title)  

    await notice.delete()  
    await delete_tracked_messages(client, chat_id)  
    if os.path.exists(file_path):  
        os.remove(file_path)  

except Exception as e:  
    await notice.edit(f"❌ Error: {str(e)}")  
    await delete_tracked_messages(client, chat_id)

@app.on_message(filters.text & filters.private)
async def token_response(client, message):
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

print("🔥 बोट स्टार्ट हो रहा है... FFmpeg चेक कर रहा हूं")
ffmpeg_path = get_ffmpeg_path()
if ffmpeg_path:
print(f"✅ FFmpeg मिल गया: {ffmpeg_path}")
else:
print("ffmpeg not found")

app.run()
