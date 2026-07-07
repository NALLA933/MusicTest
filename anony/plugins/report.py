import time
import asyncio

from pymongo import MongoClient, ReturnDocument

from pyrogram import filters
from pyrogram.types import Message

from anony import app
from config import Config

config = Config()

mongo = MongoClient(config.MONGO_URL)
db = mongo["AviaxMusic"]
reports_col = db["reports"]
counters_col = db["counters"]

PREFIXES         = ["!", "/", ".", "@", ":"]
REPORT_COMMANDS  = ["report", "comment"]
RESOLVE_COMMANDS = ["resolve", "fix", "close"]

COOLDOWN_SECONDS = 30
last_report: dict[int, float] = {}


def multi_prefix(commands: list[str]):
    triggers = [p + c for p in PREFIXES for c in commands]

    async def _check(_, __, message: Message) -> bool:
        return bool(message.text) and any(message.text.startswith(t) for t in triggers)

    return filters.create(_check)


def extract_body(text: str, commands: list[str]) -> str | None:
    for prefix in PREFIXES:
        for cmd in commands:
            trigger = prefix + cmd
            if text.startswith(trigger):
                body = text[len(trigger):].strip()
                return body or None
    return None


def _generate_ticket_id_sync() -> str:
    result = counters_col.find_one_and_update(
        {"_id": "ticket_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return str(result["seq"])


async def generate_ticket_id() -> str:
    return await asyncio.to_thread(_generate_ticket_id_sync)


def _save_report_sync(doc: dict) -> None:
    reports_col.insert_one(doc)


async def save_report(ticket_id: str, m: Message, reason: str) -> None:
    user = m.from_user
    chat = m.chat

    doc = {
        "ticket_id": ticket_id,
        "reason": reason,
        "status": "open",
        "created_at": time.time(),
        "user_id": user.id,
        "user_name": user.first_name or "",
        "username": user.username,
        "chat_id": chat.id,
        "chat_title": chat.title or "N/A",
    }

    if m.reply_to_message and m.reply_to_message.from_user:
        target = m.reply_to_message.from_user
        doc["target_user_id"] = target.id
        doc["target_user_name"] = target.first_name or ""
        doc["target_username"] = target.username

    await asyncio.to_thread(_save_report_sync, doc)


def build_log_text(ticket_id: str, m: Message, reason: str) -> str:
    user = m.from_user
    chat = m.chat

    full_name = user.first_name or ""
    if user.last_name:
        full_name += f" {user.last_name}"
    username = f"@{user.username}" if user.username else "ɴᴏɴᴇ"

    text = (
        "⌈ ɴᴇᴡ ʀᴇᴘᴏʀᴛ ⌋\n\n"
        f'◉ ᴛɪᴄᴋᴇᴛ ɪᴅ: "{ticket_id}"\n'
        f"◉ ʀᴇᴀsᴏɴ: {reason}\n\n"
        "◌ ʀᴇᴘᴏʀᴛᴇᴅ ʙʏ\n"
        f"◉ ɴᴀᴍᴇ: {full_name}\n"
        f"◉ ᴜsᴇʀɴᴀᴍᴇ: {username}\n"
        f'◉ ᴜsᴇʀ ɪᴅ: "{user.id}"\n\n'
        "◌ ɢʀᴏᴜᴘ\n"
        f"◉ ɢʀᴏᴜᴘ ɴᴀᴍᴇ: {chat.title or 'ɴ/ᴀ'}\n"
        f'◉ ɢʀᴏᴜᴘ ɪᴅ: "{chat.id}"'
    )

    if m.reply_to_message and m.reply_to_message.from_user:
        target = m.reply_to_message.from_user
        target_name = target.first_name or ""
        if target.last_name:
            target_name += f" {target.last_name}"
        target_username = f"@{target.username}" if target.username else "ɴᴏɴᴇ"

        text += (
            "\n\n◌ ʀᴇᴘᴏʀᴛᴇᴅ ᴜsᴇʀ\n"
            f"◉ ɴᴀᴍᴇ: {target_name}\n"
            f"◉ ᴜsᴇʀɴᴀᴍᴇ: {target_username}\n"
            f'◉ ᴜsᴇʀ ɪᴅ: "{target.id}"'
        )

    text += (
        "\n\n◌ ᴛᴏ ʀᴇsᴏʟᴠᴇ\n"
        f"<code>/resolve {ticket_id} your reply here</code>"
    )

    return text


@app.on_message(multi_prefix(REPORT_COMMANDS) & filters.group & ~app.bl_users)
async def report_handler(_, m: Message):
    if not m.from_user:
        return await m.reply_text(
            "⚠️ <b>ᴀɴᴏɴʏᴍᴏᴜs ᴀᴅᴍɪɴs ᴄᴀɴ'ᴛ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.</b>"
        )

    text = m.text or ""
    reason = extract_body(text, REPORT_COMMANDS)

    if not reason:
        return await m.reply_text(
            "⚠️ <b>ᴘʟᴇᴀsᴇ ᴅᴇsᴄʀɪʙᴇ ᴛʜᴇ ᴘʀᴏʙʟᴇᴍ.</b>\n"
            "<i>ᴇxᴀᴍᴘʟᴇ: /report ʙᴏᴛ ɪs ɴᴏᴛ ᴘʟᴀʏɪɴɢ ᴀᴜᴅɪᴏ</i>"
        )

    user_id = m.from_user.id
    now = time.monotonic()
    last = last_report.get(user_id, 0)
    if now - last < COOLDOWN_SECONDS:
        wait = int(COOLDOWN_SECONDS - (now - last))
        return await m.reply_text(
            f"⏳ <b>ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ {wait}s ʙᴇꜰᴏʀᴇ sᴇɴᴅɪɴɢ ᴀɴᴏᴛʜᴇʀ ʀᴇᴘᴏʀᴛ.</b>"
        )

    if not config.LOGGER_ID:
        return await m.reply_text(
            "⚠️ <b>ʀᴇᴘᴏʀᴛ sʏsᴛᴇᴍ ɪs ɴᴏᴛ ᴄᴏɴꜰɪɢᴜʀᴇᴅ.</b>"
        )

    ticket_id = await generate_ticket_id()

    try:
        await save_report(ticket_id, m, reason)
    except Exception:
        return await m.reply_text(
            "❌ <b>ꜰᴀɪʟᴇᴅ ᴛᴏ sᴀᴠᴇ ʀᴇᴘᴏʀᴛ. ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.</b>"
        )

    log_text = build_log_text(ticket_id, m, reason)

    try:
        await app.send_message(config.LOGGER_ID, log_text, disable_web_page_preview=True)
    except Exception:
        return await m.reply_text(
            "❌ <b>ꜰᴀɪʟᴇᴅ ᴛᴏ sᴇɴᴅ ʀᴇᴘᴏʀᴛ. ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.</b>"
        )

    last_report[user_id] = now
    await m.reply_text(
        "✅ <b>ʏᴏᴜʀ ʀᴇᴘᴏʀᴛ ʜᴀs ʙᴇᴇɴ sᴇɴᴛ.</b>\n"
        f'◉ ᴛɪᴄᴋᴇᴛ ɪᴅ: "{ticket_id}"\n'
        "<i>ᴋᴇᴇᴘ ᴛʜɪs ɪᴅ ꜰᴏʀ ʀᴇꜰᴇʀᴇɴᴄᴇ.</i>"
    )


def is_sudo(user_id: int) -> bool:
    return user_id == config.OWNER_ID or user_id in getattr(app, "sudoers", [])


def _find_report_sync(ticket_id: str) -> dict | None:
    return reports_col.find_one({"ticket_id": ticket_id})


def _delete_report_sync(ticket_id: str) -> None:
    reports_col.delete_one({"ticket_id": ticket_id})


@app.on_message(multi_prefix(RESOLVE_COMMANDS) & filters.private & ~app.bl_users)
async def resolve_handler(_, m: Message):
    if not m.from_user or not is_sudo(m.from_user.id):
        return await m.reply_text("🚫 <b>sᴜᴅᴏ ᴜsᴇʀs ᴏɴʟʏ.</b>")

    text = m.text or ""
    body = extract_body(text, RESOLVE_COMMANDS)

    if not body:
        return await m.reply_text(
            "⚠️ <b>ᴜsᴀɢᴇ:</b>\n<code>/resolve 1 your reply here</code>"
        )

    parts = body.split(maxsplit=1)
    if len(parts) < 2:
        return await m.reply_text(
            "⚠️ <b>ᴘʟᴇᴀsᴇ ɪɴᴄʟᴜᴅᴇ ᴀ ʀᴇᴘʟʏ ᴍᴇssᴀɢᴇ ᴀꜰᴛᴇʀ ᴛʜᴇ ᴛɪᴄᴋᴇᴛ ɪᴅ.</b>"
        )

    ticket_id, reply_msg = parts[0], parts[1]

    report = await asyncio.to_thread(_find_report_sync, ticket_id)
    if not report:
        return await m.reply_text(f'❌ <b>ɴᴏ ʀᴇᴘᴏʀᴛ ꜰᴏᴜɴᴅ ꜰᴏʀ ᴛɪᴄᴋᴇᴛ:</b> "{ticket_id}"')

    chat_id = report["chat_id"]
    user_id = report["user_id"]
    user_name = report.get("user_name") or "User"
    mention = f'<a href="tg://user?id={user_id}">{user_name}</a>'

    notify_text = (
        "⌈ ᴛɪᴄᴋᴇᴛ ʀᴇsᴏʟᴠᴇᴅ ⌋\n\n"
        f"◉ {mention}, ʏᴏᴜʀ ʀᴇᴘᴏʀᴛᴇᴅ ɪssᴜᴇ ʜᴀs ʙᴇᴇɴ ꜰɪxᴇᴅ.\n"
        f'◉ ᴛɪᴄᴋᴇᴛ ɪᴅ: "{ticket_id}"\n'
        f"◉ ɴᴏᴛᴇ: {reply_msg}"
    )

    try:
        await app.send_message(chat_id, notify_text)
    except Exception as e:
        return await m.reply_text(f"❌ <b>ꜰᴀɪʟᴇᴅ ᴛᴏ ɴᴏᴛɪꜰʏ ᴜsᴇʀ:</b> <code>{e}</code>")

    await asyncio.to_thread(_delete_report_sync, ticket_id)

    await m.reply_text(f'✅ <b>ᴛɪᴄᴋᴇᴛ "{ticket_id}" ᴍᴀʀᴋᴇᴅ ᴀs ʀᴇsᴏʟᴠᴇᴅ ᴀɴᴅ ᴜsᴇʀ ɴᴏᴛɪꜰɪᴇᴅ.</b>')
