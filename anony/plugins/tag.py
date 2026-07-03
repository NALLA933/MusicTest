import asyncio
import logging
import time

from pyrogram import filters, enums
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait, UserNotParticipant, ChatAdminRequired
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from anony import app

logger = logging.getLogger("tagall")

PREFIXES        = ["!", "/", ".", "@", ":"]
TAG_COMMANDS    = ["utag", "all", "mention", "tag", "tagall", "mentionall"]
STOP_COMMANDS   = ["cancel", "ustop", "stoptag", "canceltag"]
BATCH_SIZE      = 5
BATCH_DELAY     = 4.5
PROGRESS_EVERY  = 30
ADMIN_CACHE_TTL = 120

active_tags: set[int]                                  = set()
admin_cache: dict[tuple[int, int], tuple[bool, float]] = {}


def multi_prefix(commands: list[str]):
    triggers = [p + c for p in PREFIXES for c in commands]

    async def _check(_, __, message: Message) -> bool:
        return bool(message.text) and any(message.text.startswith(t) for t in triggers)

    return filters.create(_check)


def extract_custom_text(text: str) -> str | None:
    for prefix in PREFIXES:
        for cmd in TAG_COMMANDS:
            trigger = prefix + cmd
            if text.startswith(trigger):
                body = text[len(trigger):].strip()
                for flag in ("--admins", "--recent", "--bots"):
                    body = body.replace(flag, "").strip()
                return body or None
    return None


def stop_button(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⛔ sᴛᴏᴘ ᴛᴀɢɢɪɴɢ", callback_data=f"stoptag_{chat_id}")
    ]])


def parse_chat_id(data: str) -> int | None:
    try:
        return int(data.split("_", 1)[1])
    except (IndexError, ValueError):
        return None


async def is_admin(chat_id: int, user_id: int) -> bool:
    if user_id in getattr(app, "sudoers", []):
        return True

    key = (chat_id, user_id)
    cached = admin_cache.get(key)
    if cached:
        result, ts = cached
        if time.monotonic() - ts < ADMIN_CACHE_TTL:
            return result

    try:
        member = await app.get_chat_member(chat_id, user_id)
        result = member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)
    except UserNotParticipant:
        result = False
    except Exception as e:
        logger.error("Admin check failed uid=%s cid=%s: %s", user_id, chat_id, e)
        result = False

    admin_cache[key] = (result, time.monotonic())
    return result


async def react_ack(message: Message) -> None:
    try:
        await app.send_reaction(
            chat_id=message.chat.id,
            message_id=message.id,
            emoji="🍓",
        )
    except Exception:
        pass


async def send_batch(
    chat_id: int,
    reply_to_id: int | None,
    custom_text: str | None,
    batch: list[str],
    start: int,
    end: int,
    *,
    retries: int = 3,
) -> None:
    lines = "\n".join(f"⟣ › {mention}" for mention in batch)

    parts = []
    if custom_text:
        parts.append(custom_text)
    parts.append(lines)
    parts.append(f"<b>ᴛᴀɢɢᴇᴅ:</b> <code>{start}–{end}</code>")
    text = "\n\n".join(parts)

    kwargs: dict = {"disable_web_page_preview": True}
    if reply_to_id:
        kwargs["reply_to_message_id"] = reply_to_id

    for attempt in range(retries):
        try:
            await app.send_message(chat_id, text, **kwargs)
            return
        except FloodWait as e:
            logger.warning("FloodWait %ss batch %s-%s attempt %s", e.value + 2, start, end, attempt + 1)
            await asyncio.sleep(e.value + 2)
        except Exception as e:
            logger.error("Batch send failed attempt=%s cid=%s: %s", attempt + 1, chat_id, e)
            await asyncio.sleep(1)


@app.on_message(multi_prefix(TAG_COMMANDS) & filters.group & ~app.bl_users)
async def tag_all(_, m: Message):
    chat_id = m.chat.id

    # FIX: m.from_user can be None when the sender is an anonymous admin
    # or the message comes from a linked channel. Guard before using .id
    if not m.from_user:
        return await m.reply_text(
            "🚫 <b>ᴀɴᴏɴʏᴍᴏᴜs ᴀᴅᴍɪɴs ᴄᴀɴ'ᴛ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.</b>\n"
            "<i>ᴘʟᴇᴀsᴇ ᴅɪsᴀʙʟᴇ 'sᴇɴᴅ ᴀs' ᴀɴᴏɴʏᴍᴏᴜs ᴀᴅᴍɪɴ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.</i>"
        )

    if not await is_admin(chat_id, m.from_user.id):
        return await m.reply_text("🚫 <b>ᴀᴅᴍɪɴs ᴏɴʟʏ.</b>")

    if chat_id in active_tags:
        return await m.reply_text(
            "⚠️ <b>ᴛᴀɢɢɪɴɢ ᴀʟʀᴇᴀᴅʏ ɪɴ ᴘʀᴏɢʀᴇss.</b>",
            reply_markup=stop_button(chat_id),
        )

    text = m.text or ""

    member_filter = None
    filter_label  = "ᴀʟʟ ᴍᴇᴍʙᴇʀs"

    if "--admins" in text:
        member_filter = enums.ChatMembersFilter.ADMINISTRATORS
        filter_label  = "ᴀᴅᴍɪɴs ᴏɴʟʏ"
    elif "--recent" in text:
        member_filter = enums.ChatMembersFilter.RECENT
        filter_label  = "ʀᴇᴄᴇɴᴛ ᴍᴇᴍʙᴇʀs"
    elif "--bots" in text:
        member_filter = enums.ChatMembersFilter.BOTS
        filter_label  = "ʙᴏᴛs ᴏɴʟʏ"

    custom_text = extract_custom_text(text)
    reply_to_id = m.reply_to_message.id if m.reply_to_message else None

    active_tags.add(chat_id)
    await react_ack(m)

    batch: list[str] = []
    total = 0
    sent  = 0

    progress = await m.reply_text(
        f"⏳ <b>sᴛᴀʀᴛɪɴɢ ᴛᴀɢɢɪɴɢ…</b> (<i>{filter_label}</i>)",
        reply_markup=stop_button(chat_id),
    )

    try:
        get_members_kwargs: dict = {"chat_id": chat_id}
        if member_filter is not None:
            get_members_kwargs["filter"] = member_filter

        async for member in app.get_chat_members(**get_members_kwargs):
            if chat_id not in active_tags:
                await progress.edit_text("⛔ <b>ᴛᴀɢɢɪɴɢ sᴛᴏᴘᴘᴇᴅ.</b>")
                return

            user = member.user
            if not user or user.is_bot or user.is_deleted:
                continue

            batch.append(user.mention)
            total += 1

            if len(batch) == BATCH_SIZE:
                sent += BATCH_SIZE
                await send_batch(chat_id, reply_to_id, custom_text, batch, sent - BATCH_SIZE + 1, sent)
                batch.clear()

                if sent % PROGRESS_EVERY == 0:
                    try:
                        await progress.edit_text(
                            f"⏳ <b>ᴛᴀɢɢɪɴɢ ɪɴ ᴘʀᴏɢʀᴇss…</b>\n"
                            f"<b>ᴛᴀɢɢᴇᴅ sᴏ ꜰᴀʀ:</b> <code>{sent}</code>",
                            reply_markup=stop_button(chat_id),
                        )
                    except Exception:
                        pass

                await asyncio.sleep(BATCH_DELAY)

        if batch and chat_id in active_tags:
            sent += len(batch)
            await send_batch(chat_id, reply_to_id, custom_text, batch, sent - len(batch) + 1, sent)

        if chat_id in active_tags:
            try:
                await progress.edit_text(
                    f"✅ <b>ᴛᴀɢɢɪɴɢ ᴄᴏᴍᴘʟᴇᴛᴇ!</b>\n"
                    f"<b>ᴛᴏᴛᴀʟ ᴛᴀɢɢᴇᴅ:</b> <code>{total}</code>"
                )
            except Exception:
                pass

    except FloodWait as e:
        await progress.edit_text(
            f"⚠️ <b>ꜰʟᴏᴏᴅ ᴡᴀɪᴛ:</b> <code>{e.value}s</code>\n<i>ʀᴇsᴜᴍɪɴɢ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ…</i>"
        )
        await asyncio.sleep(e.value + 2)
    except ChatAdminRequired:
        await progress.edit_text("❌ <b>ʙᴏᴛ ɴᴇᴇᴅs ᴀᴅᴍɪɴ ʀɪɢʜᴛs ᴛᴏ ꜰᴇᴛᴄʜ ᴍᴇᴍʙᴇʀs.</b>")
    except Exception as e:
        logger.exception("Tagging failed in chat %s", chat_id)
        await progress.edit_text(f"❌ <b>ᴇʀʀᴏʀ:</b> <code>{e}</code>")
    finally:
        active_tags.discard(chat_id)


@app.on_message(multi_prefix(STOP_COMMANDS) & filters.group & ~app.bl_users)
async def stop_tag(_, m: Message):
    chat_id = m.chat.id

    if chat_id not in active_tags:
        return await m.reply_text("ℹ️ <b>ɴᴏ ᴛᴀɢɢɪɴɢ ɪɴ ᴘʀᴏɢʀᴇss.</b>")

    # FIX: same None guard here — stop_tag also reads m.from_user.id
    if not m.from_user:
        return await m.reply_text("🚫 <b>ᴀɴᴏɴʏᴍᴏᴜs ᴀᴅᴍɪɴs ᴄᴀɴ'ᴛ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ.</b>")

    if not await is_admin(chat_id, m.from_user.id):
        return await m.reply_text("🚫 <b>ᴀᴅᴍɪɴs ᴏɴʟʏ.</b>")

    active_tags.discard(chat_id)
    await m.reply_text("✅ <b>ᴛᴀɢɢɪɴɢ sᴛᴏᴘᴘᴇᴅ.</b>")


@app.on_callback_query(filters.regex(r"^stoptag_"))
async def cb_stop_tag(_, cq: CallbackQuery):
    chat_id = parse_chat_id(cq.data)
    if chat_id is None:
        return await cq.answer("ɪɴᴠᴀʟɪᴅ ᴅᴀᴛᴀ.", show_alert=True)

    # cq.from_user is always present on callback queries, no guard needed here
    if not await is_admin(chat_id, cq.from_user.id):
        return await cq.answer("ᴀᴅᴍɪɴs ᴏɴʟʏ.", show_alert=True)

    if chat_id not in active_tags:
        await cq.answer("ɴᴏ ᴀᴄᴛɪᴠᴇ ᴛᴀɢɢɪɴɢ.", show_alert=True)
        try:
            await cq.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    active_tags.discard(chat_id)
    await cq.answer("sᴛᴏᴘᴘᴇᴅ.", show_alert=False)
    try:
        await cq.message.edit_text(
            "⛔ <b>ᴛᴀɢɢɪɴɢ sᴛᴏᴘᴘᴇᴅ ʙʏ</b> " + cq.from_user.mention
        )
    except Exception:
        pass
