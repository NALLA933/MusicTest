from asyncio import sleep
from pyrogram import filters
from pyrogram.enums import ChatType, ChatMemberStatus
from pyrogram.errors import MessageDeleteForbidden, RPCError, UserNotParticipant
from pyrogram.types import Message
from anony import app

OWNER_ID = [5147822244]


async def is_admin(chat_id: int, user_id: int) -> bool:
    if user_id in OWNER_ID:
        return True

    try:
        member = await app.get_chat_member(chat_id, user_id)
        if member.status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            return True
        return False
    except UserNotParticipant:
        return False
    except Exception:
        return False


async def can_delete_messages(chat_id: int, user_id: int) -> bool:
    if user_id in OWNER_ID:
        return True

    try:
        member = await app.get_chat_member(chat_id, user_id)

        if member.status == ChatMemberStatus.OWNER:
            return True

        if member.status == ChatMemberStatus.ADMINISTRATOR:
            if member.privileges and member.privileges.can_delete_messages:
                return True
            return False

        return False

    except UserNotParticipant:
        return False
    except Exception:
        return False


@app.on_message(filters.command("purge") & filters.group & ~app.bl_users)
async def purge_messages(_, m: Message):
    if m.chat.type not in (ChatType.SUPERGROUP, ChatType.GROUP):
        return await m.reply_text("<b>Only works in groups</b>")

    if not m.reply_to_message:
        return await m.reply_text("<b>Reply to a message to start purging</b>")

    if not await can_delete_messages(m.chat.id, m.from_user.id):
        return await m.reply_text("<b>You need delete messages permission</b>")

    try:
        msg_ids = list(range(m.reply_to_message.id, m.id + 1))
        status = await m.reply_text(f"<b>Purging {len(msg_ids)} messages...</b>")

        deleted = 0
        for i in range(0, len(msg_ids), 100):
            chunk = msg_ids[i:i + 100]
            try:
                await app.delete_messages(m.chat.id, chunk, revoke=True)
                deleted += len(chunk)
            except Exception:
                pass

        await status.edit_text(f"<b>Deleted {deleted} messages</b>")
        await sleep(2)
        await status.delete()

    except MessageDeleteForbidden:
        await m.reply_text("<b>Missing permissions to delete messages</b>")
    except RPCError as e:
        await m.reply_text(f"<b>Error:</b> <code>{e}</code>")


@app.on_message(filters.command("spurge") & filters.group & ~app.bl_users)
async def spurge_messages(_, m: Message):
    if m.chat.type not in (ChatType.SUPERGROUP, ChatType.GROUP):
        return

    if not m.reply_to_message:
        return

    if not await can_delete_messages(m.chat.id, m.from_user.id):
        return

    try:
        msg_ids = list(range(m.reply_to_message.id, m.id + 1))

        for i in range(0, len(msg_ids), 100):
            chunk = msg_ids[i:i + 100]
            try:
                await app.delete_messages(m.chat.id, chunk, revoke=True)
            except Exception:
                pass

    except Exception:
        pass


@app.on_message(filters.command("del") & filters.group & ~app.bl_users)
async def delete_message(_, m: Message):
    if m.chat.type not in (ChatType.SUPERGROUP, ChatType.GROUP):
        return await m.reply_text("<b>Only works in groups</b>")

    if not m.reply_to_message:
        return await m.reply_text("<b>Reply to a message to delete it</b>")

    if not await can_delete_messages(m.chat.id, m.from_user.id):
        return await m.reply_text("<b>You need delete messages permission</b>")

    try:
        await app.delete_messages(m.chat.id, [m.reply_to_message.id, m.id])
    except MessageDeleteForbidden:
        await m.reply_text("<b>Missing permissions to delete messages</b>")
    except RPCError as e:
        await m.reply_text(f"<b>Error:</b> <code>{e}</code>")


@app.on_message(filters.command("purgeme") & ~app.bl_users)
async def purge_my_messages(_, m: Message):
    if len(m.command) < 2:
        return await m.reply_text("<b>Usage:</b> <code>/purgeme count</code>")

    try:
        count = int(m.command[1])
        if count < 1 or count > 100:
            return await m.reply_text("<b>Count must be between 1-100</b>")
    except ValueError:
        return await m.reply_text("<b>Invalid number</b>")

    deleted = 0
    async for msg in app.get_chat_history(m.chat.id, limit=count + 1):
        if msg.from_user and msg.from_user.id == m.from_user.id:
            try:
                await msg.delete()
                deleted += 1
            except Exception:
                pass

    status = await m.reply_text(f"<b>Deleted {deleted} of your messages</b>")
    await sleep(2)
    await status.delete()