from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.errors import ChatAdminRequired
from pyrogram.types import (
    Message,
    User,
    Chat,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from anony import app
from config import Config

config = Config()

PREFIXES      = ["!", "/", ".", "@", ":"]
INFO_COMMANDS = ["info", "id", "userinfo", "whois"]


def multi_prefix(commands: list[str]):
    triggers = [p + c for p in PREFIXES for c in commands]

    async def _check(_, __, message: Message) -> bool:
        return bool(message.text) and any(message.text.startswith(t) for t in triggers)

    return filters.create(_check)


async def get_group_link(chat: Chat) -> tuple[str, str | None]:
    if chat.username:
        return "ᴘᴜʙʟɪᴄ", f"https://t.me/{chat.username}"

    link = chat.invite_link
    if not link:
        try:
            link = await app.export_chat_invite_link(chat.id)
        except ChatAdminRequired:
            link = None
        except Exception:
            link = None

    return "ᴘʀɪᴠᴀᴛᴇ", link


def build_info_text(user: User, chat: Chat, group_type: str, group_link: str | None) -> str:
    full_name = user.first_name or ""
    if user.last_name:
        full_name += f" {user.last_name}"

    username = f"@{user.username}" if user.username else "ɴᴏɴᴇ"

    text = (
        "⌈ ɪɴꜰᴏ ⌋\n\n"
        "◌ ᴜsᴇʀ ᴘʀᴏꜰɪʟᴇ\n\n"
        f"◉ ɴᴀᴍᴇ: {full_name}\n"
        f"◉ ᴜsᴇʀɴᴀᴍᴇ: {username}\n"
        f'◉ ᴛᴇʟᴇɢʀᴀᴍ ɪᴅ: "{user.id}"\n'
        f'◉ ɢʀᴏᴜᴘ ɪᴅ: "{chat.id}"\n'
        f"◉ ɢʀᴏᴜᴘ ᴛʏᴘᴇ: {group_type}"
    )

    if group_link:
        text += f"\n◉ ɢʀᴏᴜᴘ ʟɪɴᴋ: {group_link}"

    return text


def support_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🛠 sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ", url=config.SUPPORT_CHAT)]]
    )


@app.on_message(multi_prefix(INFO_COMMANDS) & filters.group & ~app.bl_users)
async def user_info(_, m: Message):
    chat = m.chat
    target_user = None

    parts = m.text.split(maxsplit=1)
    if len(parts) > 1:
        query = parts[1].strip()
        if query.startswith("@"):
            query = query[1:]

        try:
            target_user = await app.get_users(query)
        except Exception:
            return await m.reply_text(
                "⚠️ <b>ᴜsᴇʀ ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>\n"
                "<i>ᴄʜᴇᴄᴋ ᴛʜᴇ ᴜsᴇʀɴᴀᴍᴇ/ɪᴅ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.</i>"
            )

    elif m.reply_to_message and m.reply_to_message.from_user:
        target_user = m.reply_to_message.from_user

    elif m.from_user:
        target_user = m.from_user

    if not target_user:
        return await m.reply_text(
            "⚠️ <b>ᴄᴏᴜʟᴅ ɴᴏᴛ ꜰᴇᴛᴄʜ ᴜsᴇʀ ɪɴꜰᴏ.</b>\n"
            "<i>ᴛʜᴇ sᴇɴᴅᴇʀ ɪs ᴀɴᴏɴʏᴍᴏᴜs ᴏʀ ᴜsᴇʀ ᴅᴀᴛᴀ ɪs ᴜɴᴀᴠᴀɪʟᴀʙʟᴇ.</i>"
        )

    group_type, group_link = await get_group_link(chat)
    text = build_info_text(target_user, chat, group_type, group_link)

    await m.reply_text(
        text,
        disable_web_page_preview=True,
        reply_markup=support_button(),
    )
