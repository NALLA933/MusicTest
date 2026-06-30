import re
import time

from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import filters
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message

from anony import app
from config import Config

mongo = AsyncIOMotorClient(Config().MONGO_URL)
afk_db = mongo["AnonyBot"]["afk"]


def get_readable_time(seconds: int) -> str:
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    result = []
    for label, length in periods:
        if seconds >= length:
            value, seconds = divmod(seconds, length)
            result.append(f"{value}{label}")
    return " ".join(result) if result else "0s"


async def add_afk(user_id: int, reason: str | None) -> None:
    await afk_db.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "time": time.time(), "reason": reason}},
        upsert=True,
    )


async def is_afk(user_id: int):
    data = await afk_db.find_one({"user_id": user_id})
    if data:
        return True, data
    return False, None


async def remove_afk(user_id: int) -> None:
    await afk_db.delete_one({"user_id": user_id})


@app.on_message(filters.command(["afk", "brb"], prefixes=["/", "!"]))
async def active_afk(_, message: Message):
    if message.sender_chat or not message.from_user:
        return

    user_id = message.from_user.id

    verifier, data = await is_afk(user_id)
    if verifier:
        await remove_afk(user_id)
        seenago = get_readable_time(int(time.time() - data["time"]))
        if data.get("reason"):
            await message.reply_text(
                f"**{message.from_user.first_name}** ɪs ʙᴀᴄᴋ ᴏɴʟɪɴᴇ ᴀɴᴅ ᴡᴀs ᴀᴡᴀʏ ꜰᴏʀ {seenago}\n\n"
                f"ʀᴇᴀsᴏɴ: `{data['reason']}`",
                disable_web_page_preview=True,
            )
        else:
            await message.reply_text(
                f"**{message.from_user.first_name}** ɪs ʙᴀᴄᴋ ᴏɴʟɪɴᴇ ᴀɴᴅ ᴡᴀs ᴀᴡᴀʏ ꜰᴏʀ {seenago}",
                disable_web_page_preview=True,
            )

    reason = None
    if len(message.command) > 1:
        reason = message.text.split(None, 1)[1].strip()[:100]

    await add_afk(user_id, reason)
    await message.reply_text(f"**{message.from_user.first_name}** ɪs ɴᴏᴡ ᴀꜰᴋ!")


@app.on_message(~filters.me & ~filters.bot & ~filters.via_bot, group=1)
async def afk_watcher(_, message: Message):
    if message.sender_chat or not message.from_user:
        return

    if message.entities:
        possible = ["/afk", "/brb"]
        message_text = message.text or message.caption or ""
        for entity in message.entities:
            if entity.type == MessageEntityType.BOT_COMMAND:
                cmd = message_text[entity.offset: entity.offset + entity.length].split("@")[0].lower()
                if cmd in possible:
                    return

    user_id = message.from_user.id
    user_name = message.from_user.first_name
    msg = ""
    replied_user_id = 0

    verifier, data = await is_afk(user_id)
    if verifier:
        await remove_afk(user_id)
        seenago = get_readable_time(int(time.time() - data["time"]))
        if data.get("reason"):
            msg += f"**{user_name[:25]}** ɪs ʙᴀᴄᴋ ᴏɴʟɪɴᴇ ᴀɴᴅ ᴡᴀs ᴀᴡᴀʏ ꜰᴏʀ {seenago}\n\nʀᴇᴀsᴏɴ: `{data['reason']}`\n\n"
        else:
            msg += f"**{user_name[:25]}** ɪs ʙᴀᴄᴋ ᴏɴʟɪɴᴇ ᴀɴᴅ ᴡᴀs ᴀᴡᴀʏ ꜰᴏʀ {seenago}\n\n"

    if message.reply_to_message and message.reply_to_message.from_user:
        replied_user = message.reply_to_message.from_user
        replied_user_id = replied_user.id
        verifier, data = await is_afk(replied_user_id)
        if verifier:
            seenago = get_readable_time(int(time.time() - data["time"]))
            if data.get("reason"):
                msg += f"**{replied_user.first_name[:25]}** ɪs ᴀꜰᴋ sɪɴᴄᴇ {seenago}\n\nʀᴇᴀsᴏɴ: `{data['reason']}`\n\n"
            else:
                msg += f"**{replied_user.first_name[:25]}** ɪs ᴀꜰᴋ sɪɴᴄᴇ {seenago}\n\n"

    if message.entities:
        text = message.text or ""
        mentioned_usernames = re.findall(r"@([_0-9a-zA-Z]+)", text)
        idx = 0
        for entity in message.entities:
            if entity.type == MessageEntityType.MENTION:
                if idx >= len(mentioned_usernames):
                    idx += 1
                    continue
                try:
                    user = await app.get_users(mentioned_usernames[idx])
                except Exception:
                    idx += 1
                    continue
                idx += 1
                if user.id == replied_user_id:
                    continue
                verifier, data = await is_afk(user.id)
                if verifier:
                    seenago = get_readable_time(int(time.time() - data["time"]))
                    if data.get("reason"):
                        msg += f"**{user.first_name[:25]}** ɪs ᴀꜰᴋ sɪɴᴄᴇ {seenago}\n\nʀᴇᴀsᴏɴ: `{data['reason']}`\n\n"
                    else:
                        msg += f"**{user.first_name[:25]}** ɪs ᴀꜰᴋ sɪɴᴄᴇ {seenago}\n\n"

            elif entity.type == MessageEntityType.TEXT_MENTION:
                tm_user = entity.user
                if not tm_user or tm_user.id == replied_user_id:
                    continue
                verifier, data = await is_afk(tm_user.id)
                if verifier:
                    seenago = get_readable_time(int(time.time() - data["time"]))
                    if data.get("reason"):
                        msg += f"**{tm_user.first_name[:25]}** ɪs ᴀꜰᴋ sɪɴᴄᴇ {seenago}\n\nʀᴇᴀsᴏɴ: `{data['reason']}`\n\n"
                    else:
                        msg += f"**{tm_user.first_name[:25]}** ɪs ᴀꜰᴋ sɪɴᴄᴇ {seenago}\n\n"

    if msg:
        try:
            await message.reply_text(msg.strip(), disable_web_page_preview=True)
        except Exception:
            pass
