import asyncio
import logging

from pyrogram import filters, enums
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait, ChatAdminRequired
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ChatPermissions,
)

from anony import app

logger = logging.getLogger("banall")

PREFIXES        = ["!", "/", ".", "@", ":"]
BAN_COMMANDS    = ["banall"]
KICK_COMMANDS   = ["kickall"]
UNBAN_COMMANDS  = ["unbanall"]
STOP_COMMANDS   = ["stopall"]
BATCH_DELAY     = 0.6
PROGRESS_EVERY  = 25

active_ops: dict[int, str] = {}

BANNED_RIGHTS = ChatPermissions()


def multi_prefix(commands: list[str]):
    triggers = [p + c for p in PREFIXES for c in commands]

    async def _check(_, __, message: Message) -> bool:
        return bool(message.text) and any(message.text.startswith(t) for t in triggers)

    return filters.create(_check)


def stop_button(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⛔ sᴛᴏᴘ", callback_data=f"stopall_{chat_id}")
    ]])


def parse_chat_id(data: str) -> int | None:
    try:
        return int(data.split("_", 1)[1])
    except (IndexError, ValueError):
        return None


def is_sudo(user_id: int) -> bool:
    return user_id in getattr(app, "sudoers", [])


async def react_ack(message: Message) -> None:
    try:
        await app.send_reaction(
            chat_id=message.chat.id,
            message_id=message.id,
            emoji="🍓",
        )
    except Exception:
        pass


async def get_admin_ids(chat_id: int) -> set[int]:
    admin_ids: set[int] = set()
    try:
        async for member in app.get_chat_members(chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
            if member.user:
                admin_ids.add(member.user.id)
    except Exception as e:
        logger.error("Failed fetching admins cid=%s: %s", chat_id, e)
    return admin_ids


async def run_purge(message: Message, op: str) -> None:
    chat_id = message.chat.id

    if not message.from_user:
        return await message.reply_text(
            "🚫 <b>ᴀɴᴏɴʏᴍᴏᴜs ᴀᴅᴍɪɴs ᴄᴀɴ'ᴛ ᴜsᴇ ᴛʜɪs.</b>\n"
            "<i>ᴅɪsᴀʙʟᴇ 'sᴇɴᴅ ᴀs' ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.</i>"
        )

    if not is_sudo(message.from_user.id):
        return await message.reply_text("🚫 <b>ᴏᴡɴᴇʀ ᴏɴʟʏ.</b>")

    if chat_id in active_ops:
        return await message.reply_text(
            f"⚠️ <b>{active_ops[chat_id].upper()} ᴀʟʀᴇᴀᴅʏ ɪɴ ᴘʀᴏɢʀᴇss.</b>",
            reply_markup=stop_button(chat_id),
        )

    try:
        me = await app.get_chat_member(chat_id, "me")
        if me.status != ChatMemberStatus.OWNER and not (
            me.privileges and (
                getattr(me.privileges, "can_restrict_members", False)
            )
        ):
            return await message.reply_text("❌ <b>ɪ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ sᴜꜰꜰɪᴄɪᴇɴᴛ ʀɪɢʜᴛs.</b>")
    except Exception:
        return await message.reply_text("❌ <b>ɪ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ sᴜꜰꜰɪᴄɪᴇɴᴛ ʀɪɢʜᴛs.</b>")

    active_ops[chat_id] = op
    await react_ack(message)

    label = {"ban": "ʙᴀɴɴɪɴɢ", "kick": "ᴋɪᴄᴋɪɴɢ", "unban": "ᴜɴʙᴀɴɴɪɴɢ"}[op]
    progress = await message.reply_text(
        f"⏳ <b>sᴛᴀʀᴛɪɴɢ {label}…</b>",
        reply_markup=stop_button(chat_id),
    )

    total = 0
    done  = 0

    try:
        if op in ("ban", "kick"):
            admin_ids = await get_admin_ids(chat_id)

            async for member in app.get_chat_members(chat_id):
                if chat_id not in active_ops:
                    await progress.edit_text(f"⛔ <b>{label} sᴛᴏᴘᴘᴇᴅ.</b>")
                    return

                user = member.user
                if not user or user.id in admin_ids or user.is_self:
                    continue

                total += 1
                try:
                    if op == "ban":
                        await app.ban_chat_member(chat_id, user.id)
                    else:
                        await app.ban_chat_member(chat_id, user.id)
                        await asyncio.sleep(0.3)
                        await app.unban_chat_member(chat_id, user.id)
                    done += 1
                except FloodWait as e:
                    logger.warning("FloodWait %ss during %s", e.value + 2, op)
                    await asyncio.sleep(e.value + 2)
                except Exception as e:
                    logger.error("%s failed uid=%s: %s", op, user.id, e)

                if done and done % PROGRESS_EVERY == 0:
                    try:
                        await progress.edit_text(
                            f"⏳ <b>{label} ɪɴ ᴘʀᴏɢʀᴇss…</b>\n"
                            f"<b>ᴅᴏɴᴇ sᴏ ꜰᴀʀ:</b> <code>{done}</code>",
                            reply_markup=stop_button(chat_id),
                        )
                    except Exception:
                        pass

                await asyncio.sleep(BATCH_DELAY)

        else:  # unban (lift bans on kicked/banned users)
            async for member in app.get_chat_members(chat_id, filter=enums.ChatMembersFilter.BANNED):
                if chat_id not in active_ops:
                    await progress.edit_text(f"⛔ <b>{label} sᴛᴏᴘᴘᴇᴅ.</b>")
                    return

                user = member.user
                if not user:
                    continue

                total += 1
                try:
                    await app.unban_chat_member(chat_id, user.id)
                    done += 1
                except FloodWait as e:
                    logger.warning("FloodWait %ss during unban", e.value + 2)
                    await asyncio.sleep(e.value + 2)
                except Exception as e:
                    logger.error("unban failed uid=%s: %s", user.id, e)

                if done and done % PROGRESS_EVERY == 0:
                    try:
                        await progress.edit_text(
                            f"⏳ <b>{label} ɪɴ ᴘʀᴏɢʀᴇss…</b>\n"
                            f"<b>ᴅᴏɴᴇ sᴏ ꜰᴀʀ:</b> <code>{done}</code>",
                            reply_markup=stop_button(chat_id),
                        )
                    except Exception:
                        pass

                await asyncio.sleep(BATCH_DELAY)

        if chat_id in active_ops:
            try:
                await progress.edit_text(
                    f"✅ <b>{label} ᴄᴏᴍᴘʟᴇᴛᴇ!</b>\n"
                    f"<b>ᴛᴏᴛᴀʟ ᴘʀᴏᴄᴇssᴇᴅ:</b> <code>{total}</code>\n"
                    f"<b>sᴜᴄᴄᴇssꜰᴜʟ:</b> <code>{done}</code>"
                )
            except Exception:
                pass

    except ChatAdminRequired:
        await progress.edit_text("❌ <b>ʙᴏᴛ ɴᴇᴇᴅs ᴀᴅᴍɪɴ ʀɪɢʜᴛs.</b>")
    except Exception as e:
        logger.exception("%s failed in chat %s", op, chat_id)
        await progress.edit_text(f"❌ <b>ᴇʀʀᴏʀ:</b> <code>{e}</code>")
    finally:
        active_ops.pop(chat_id, None)


@app.on_message(multi_prefix(BAN_COMMANDS) & filters.group & ~app.bl_users)
async def ban_all(_, m: Message):
    if not m.chat:
        return
    await run_purge(m, "ban")


@app.on_message(multi_prefix(KICK_COMMANDS) & filters.group & ~app.bl_users)
async def kick_all(_, m: Message):
    if not m.chat:
        return
    await run_purge(m, "kick")


@app.on_message(multi_prefix(UNBAN_COMMANDS) & filters.group & ~app.bl_users)
async def unban_all(_, m: Message):
    if not m.chat:
        return
    await run_purge(m, "unban")


@app.on_message(multi_prefix(STOP_COMMANDS) & filters.group & ~app.bl_users)
async def stop_all(_, m: Message):
    chat_id = m.chat.id

    if chat_id not in active_ops:
        return await m.reply_text("ℹ️ <b>ɴᴏ ᴏᴘᴇʀᴀᴛɪᴏɴ ɪɴ ᴘʀᴏɢʀᴇss.</b>")

    if not m.from_user or not is_sudo(m.from_user.id):
        return await m.reply_text("🚫 <b>ᴏᴡɴᴇʀ ᴏɴʟʏ.</b>")

    active_ops.pop(chat_id, None)
    await m.reply_text("✅ <b>sᴛᴏᴘᴘᴇᴅ.</b>")


@app.on_callback_query(filters.regex(r"^stopall_"))
async def cb_stop_all(_, cq: CallbackQuery):
    chat_id = parse_chat_id(cq.data)
    if chat_id is None:
        return await cq.answer("ɪɴᴠᴀʟɪᴅ ᴅᴀᴛᴀ.", show_alert=True)

    if not is_sudo(cq.from_user.id):
        return await cq.answer("ᴏᴡɴᴇʀ ᴏɴʟʏ.", show_alert=True)

    if chat_id not in active_ops:
        await cq.answer("ɴᴏ ᴀᴄᴛɪᴠᴇ ᴏᴘᴇʀᴀᴛɪᴏɴ.", show_alert=True)
        try:
            await cq.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    active_ops.pop(chat_id, None)
    await cq.answer("sᴛᴏᴘᴘᴇᴅ.", show_alert=False)
    try:
        await cq.message.edit_text(
            "⛔ <b>sᴛᴏᴘᴘᴇᴅ ʙʏ</b> " + cq.from_user.mention
        )
    except Exception:
        pass
