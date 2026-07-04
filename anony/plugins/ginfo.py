from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.errors import ChatAdminRequired
from pyrogram.types import (
    Message,
    Chat,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from anony import app
from config import Config

config = Config()

PREFIXES     = ["!", "/", ".", "@", ":"]
GINFO_COMMANDS = ["ginfo", "gid", "groupinfo", "chatinfo"]


def multi_prefix(commands: list[str]):
    triggers = [p + c for p in PREFIXES for c in commands]

    async def _check(_, __, message: Message) -> bool:
        return bool(message.text) and any(message.text.startswith(t) for t in triggers)

    return filters.create(_check)


def chat_type_label(chat: Chat) -> str:
    mapping = {
        ChatType.SUPERGROUP: "sᴜᴘᴇʀɢʀᴏᴜᴘ",
        ChatType.GROUP:      "ɢʀᴏᴜᴘ",
        ChatType.CHANNEL:    "ᴄʜᴀɴɴᴇʟ",
        ChatType.PRIVATE:    "ᴘʀɪᴠᴀᴛᴇ ᴄʜᴀᴛ",
        ChatType.BOT:        "ʙᴏᴛ",
    }
    return mapping.get(chat.type, "ᴜɴᴋɴᴏᴡɴ")


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


def build_group_info_text(chat: Chat, group_type: str, group_link: str | None) -> str:
    title = chat.title or "ɴᴏɴᴇ"
    username = f"@{chat.username}" if chat.username else "ɴᴏɴᴇ"
    members = chat.members_count if chat.members_count else "ɴ/ᴀ"
    description = chat.description if chat.description else "ɴᴏɴᴇ"

    text = (
        "⌈ ɢʀᴏᴜᴘ ɪɴꜰᴏ ⌋\n\n"
        "◌ ᴄʜᴀᴛ ᴘʀᴏꜰɪʟᴇ\n\n"
        f"◉ ᴛɪᴛʟᴇ: {title}\n"
        f"◉ ᴜsᴇʀɴᴀᴍᴇ: {username}\n"
        f'◉ ᴄʜᴀᴛ ɪᴅ: "{chat.id}"\n'
        f"◉ ᴄʜᴀᴛ ᴛʏᴘᴇ: {chat_type_label(chat)}\n"
        f"◉ ᴀᴄᴄᴇss: {group_type}\n"
        f"◉ ᴍᴇᴍʙᴇʀs: {members}\n"
        f"◉ ᴅᴇsᴄʀɪᴘᴛɪᴏɴ: {description}"
    )

    if group_link:
        text += f"\n◉ ɢʀᴏᴜᴘ ʟɪɴᴋ: {group_link}"

    return text


def support_button() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🛠 sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ", url=config.SUPPORT_CHAT)]]
    )


@app.on_message(multi_prefix(GINFO_COMMANDS) & ~app.bl_users)
async def group_info(_, m: Message):
    parts = m.text.split(maxsplit=1)

    target_chat = None

    if len(parts) > 1:
        query = parts[1].strip()
        if query.startswith("@"):
            query = query[1:]

        try:
            # supports both numeric id (as string) and username
            target_chat = await app.get_chat(int(query) if query.lstrip("-").isdigit() else query)
        except Exception:
            return await m.reply_text(
                "⚠️ <b>ɢʀᴏᴜᴘ ɴᴏᴛ ꜰᴏᴜɴᴅ.</b>\n"
                "<i>ᴄʜᴇᴄᴋ ᴛʜᴇ ɪᴅ/ᴜsᴇʀɴᴀᴍᴇ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ. ʙᴏᴛ ᴍᴜsᴛ ʙᴇ ᴀ ᴍᴇᴍʙᴇʀ ᴏꜰ ᴛʜᴀᴛ ɢʀᴏᴜᴘ.</i>"
            )
    else:
        # no id given -> current chat ka info
        target_chat = m.chat

    group_type, group_link = await get_group_link(target_chat)
    text = build_group_info_text(target_chat, group_type, group_link)

    await m.reply_text(
        text,
        disable_web_page_preview=True,
        reply_markup=support_button(),
    )