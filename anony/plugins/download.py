import os
import random
import asyncio
import logging

import yt_dlp
from pyrogram import filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from anony import app, config

logger = logging.getLogger("download")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

AUTO_DELETE_SECONDS = 600  # 10 minutes
COOKIE_DIR = "anony/cookies"

# query cache: key -> {"url", "title", "duration"}
search_cache: dict[str, dict] = {}


def get_cookie() -> str | None:
    if not os.path.isdir(COOKIE_DIR):
        return None
    files = [f for f in os.listdir(COOKIE_DIR) if f.endswith(".txt")]
    if not files:
        return None
    return os.path.join(COOKIE_DIR, random.choice(files))


def base_opts() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
    }
    cookie = get_cookie()
    if cookie:
        opts["cookiefile"] = cookie
    return opts


def format_duration(seconds: int) -> str:
    seconds = int(seconds or 0)
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d} ᴍɪɴ"
    return f"{minutes}:{sec:02d} ᴍɪɴ"


def short_title(title: str, limit: int = 45) -> str:
    title = title.strip()
    if len(title) <= limit:
        return title
    return title[:limit].rstrip() + "…"


def ydl_search(query: str) -> dict | None:
    opts = {
        **base_opts(),
        "default_search": "ytsearch1",
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(query, download=False)
        if "entries" in info:
            entries = info.get("entries") or []
            if not entries:
                return None
            info = entries[0]
        return info


def ydl_download(url: str, audio_only: bool) -> str:
    out_template = os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s")

    if audio_only:
        opts = {
            **base_opts(),
            "format": "bestaudio[ext=webm][acodec=opus]/bestaudio/best",
            "outtmpl": out_template,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        }
    else:
        opts = {
            **base_opts(),
            "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio)",
            "outtmpl": out_template,
            "merge_output_format": "mp4",
        }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
        if audio_only:
            base, _ = os.path.splitext(path)
            path = base + ".mp3"
        return path


def result_buttons(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🎵 ᴀᴜᴅɪᴏ", callback_data=f"dl_audio_{key}"),
        InlineKeyboardButton("🎬 ᴠɪᴅᴇᴏ", callback_data=f"dl_video_{key}"),
    ]])


async def auto_delete(message: Message, delay: int = AUTO_DELETE_SECONDS) -> None:
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


@app.on_message(filters.command(["download", "dl"], prefixes=["/", "!"]))
async def download_search(_, message: Message):
    if len(message.command) < 2:
        return await message.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b> <code>/download song name ya link</code>"
        )

    query = message.text.split(None, 1)[1].strip()
    status = await message.reply_text("🔎 <b>sᴇᴀʀᴄʜɪɴɢ…</b>")

    try:
        info = await asyncio.to_thread(ydl_search, query)
    except Exception as e:
        logger.exception("Search failed: %s", e)
        return await status.edit_text("❌ <b>sᴇᴀʀᴄʜ ꜰᴀɪʟᴇᴅ. ᴛʀʏ ᴀɢᴀɪɴ.</b>")

    if not info:
        return await status.edit_text("❌ <b>ɴᴏ ʀᴇsᴜʟᴛs ꜰᴏᴜɴᴅ.</b>")

    video_id = info.get("id", "")
    title    = info.get("title", "Unknown")
    duration_secs = int(info.get("duration", 0) or 0)
    duration = format_duration(duration_secs)
    url      = info.get("webpage_url") or info.get("url") or f"https://youtu.be/{video_id}"

    if config.DURATION_LIMIT and duration_secs > config.DURATION_LIMIT:
        limit_str = format_duration(config.DURATION_LIMIT)
        return await status.edit_text(
            f"❌ <b>ᴅᴜʀᴀᴛɪᴏɴ ʟɪᴍɪᴛ ᴇxᴄᴇᴇᴅᴇᴅ.</b>\n"
            f"ᴍᴀx ᴀʟʟᴏᴡᴇᴅ: <code>{limit_str}</code>"
        )

    requester = message.from_user.mention if message.from_user else "Anonymous"

    key = video_id or str(abs(hash(url)))
    display_title = short_title(title)
    search_cache[key] = {
        "url": url,
        "title": title,
        "display_title": display_title,
        "duration": duration,
    }

    caption = (
        f"ᴛɪᴛʟᴇ: <a href=\"{url}\">{display_title}</a>\n"
        f"\n"
        f"ᴅᴜʀᴀᴛɪᴏɴ: {duration}\n"
        f"sᴏᴜʀᴄᴇ: YouTube\n"
        f"ʀᴇQᴜᴇsᴛᴇᴅ ʙʏ: {requester}"
    )

    await status.edit_text(caption, reply_markup=result_buttons(key), disable_web_page_preview=True)


@app.on_callback_query(filters.regex(r"^dl_(audio|video)_"))
async def download_callback(_, cq: CallbackQuery):
    data = cq.data
    mode, key = data.split("_", 2)[1], data.split("_", 2)[2]

    entry = search_cache.get(key)
    if not entry:
        return await cq.answer("⚠️ Expired, search again.", show_alert=True)

    await cq.answer("⏳ Downloading…")

    audio_only = mode == "audio"

    try:
        await cq.message.edit_text(
            f"📥 <b>ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ sᴏɴɢ</b>\n\n"
            f"ᴛɪᴛʟᴇ: <a href=\"{entry['url']}\">{entry['display_title']}</a>\n"
            f"\n"
            f"ᴅᴜʀᴀᴛɪᴏɴ: {entry['duration']}\n"
            f"sᴏᴜʀᴄᴇ: YouTube\n"
            f"ʀᴇQᴜᴇsᴛᴇᴅ ʙʏ: {cq.from_user.mention}",
            disable_web_page_preview=True,
        )
    except Exception:
        pass

    file_path = None
    try:
        file_path = await asyncio.to_thread(ydl_download, entry["url"], audio_only)

        caption = f"ᴛɪᴛʟᴇ: {entry['display_title']}"

        if audio_only:
            sent = await app.send_audio(
                cq.message.chat.id,
                file_path,
                title=entry["title"],
                caption=caption,
            )
        else:
            sent = await app.send_video(
                cq.message.chat.id,
                file_path,
                caption=caption,
            )

        try:
            await cq.message.edit_text(
                f"✅ <b>ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ sᴜᴄᴄᴇssꜰᴜʟʟʏ!</b>\n\n"
                f"ᴛɪᴛʟᴇ: <a href=\"{entry['url']}\">{entry['display_title']}</a>\n"
                f"\n"
                f"<i>ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ᴀᴜᴛᴏ-ᴅᴇʟᴇᴛᴇ ɪɴ 10 ᴍɪɴ.</i>",
                disable_web_page_preview=True,
            )
        except Exception:
            pass

        asyncio.create_task(auto_delete(sent))
        asyncio.create_task(auto_delete(cq.message))

    except Exception as e:
        logger.exception("Download failed: %s", e)
        try:
            await cq.message.edit_text(f"❌ <b>ᴅᴏᴡɴʟᴏᴀᴅ ꜰᴀɪʟᴇᴅ:</b> <code>{e}</code>")
        except Exception:
            pass
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
