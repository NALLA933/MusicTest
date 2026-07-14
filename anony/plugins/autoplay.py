from pyrogram import filters, types

from anony import app, db, lang
from anony.helpers import can_manage_vc


@app.on_message(filters.command("autoplay") & filters.group & ~app.bl_users)
@lang.language()
@can_manage_vc
async def _autoplay(_, m: types.Message):
    if len(m.command) < 2:
        current = await db.get_autoplay(m.chat.id)
        status = "ᴏɴ ✅" if current else "ᴏꜰꜰ ❌"
        return await m.reply_text(f"ᴀᴜᴛᴏᴘʟᴀʏ ɪꜱ ᴄᴜʀʀᴇɴᴛʟʏ {status}\nᴜꜱᴀɢᴇ: /autoplay on|off")

    mode = m.command[1].lower()
    if mode == "on":
        await db.set_autoplay(m.chat.id, True)
        await m.reply_text("✅ ᴀᴜᴛᴏᴘʟᴀʏ ʜᴀꜱ ʙᴇᴇɴ ᴇɴᴀʙʟᴇᴅ.")
    elif mode == "off":
        await db.set_autoplay(m.chat.id, False)
        await m.reply_text("❌ ᴀᴜᴛᴏᴘʟᴀʏ ʜᴀꜱ ʙᴇᴇɴ ᴅɪꜱᴀʙʟᴇᴅ.")
    else:
        await m.reply_text("ᴜꜱᴀɢᴇ: /autoplay on|off")

