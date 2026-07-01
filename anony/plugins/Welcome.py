from logging import getLogger

from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageChops
from pyrogram import filters, enums
from pyrogram.types import (
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from anony import app

LOGGER = getLogger(__name__)

class WelDatabase:
    def __init__(self):
        self.data = {}

    async def find_one(self, chat_id):
        return chat_id in self.data

    async def add_wlcm(self, chat_id):
        if chat_id not in self.data:
            self.data[chat_id] = {"state": "off"}

    async def rm_wlcm(self, chat_id):
        if chat_id in self.data:
            del self.data[chat_id]

wlcm = WelDatabase()

class temp:
    MELCOW = {}

def circle(pfp, size=(500, 500), brightness_factor=1.0):
    pfp = pfp.resize(size, Image.LANCZOS).convert("RGBA")
    pfp = ImageEnhance.Brightness(pfp).enhance(brightness_factor)
    bigsize = (pfp.size[0] * 3, pfp.size[1] * 3)
    mask = Image.new("L", bigsize, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + bigsize, fill=255)
    mask = mask.resize(pfp.size, Image.LANCZOS)
    mask = ImageChops.darker(mask, pfp.split()[-1])
    pfp.putalpha(mask)
    return pfp

def welcomepic(pic, user, chatname, id, uname, brightness_factor=1.3):
    background = Image.open("anony/assets/wel2.png").convert("RGBA")
    pfp = Image.open(pic).convert("RGBA")
    pfp = circle(pfp, brightness_factor=brightness_factor)
    pfp = pfp.resize((300, 300))

    draw = ImageDraw.Draw(background)
    font = ImageFont.truetype("anony/assets/font.ttf", size=40)
    welcome_font = ImageFont.truetype("anony/assets/font.ttf", size=35)

    draw.text((360, 200), f"{chatname}", fill=(225, 225, 225), font=welcome_font)
    draw.text((360, 250), f"NAME: {user}", fill=(255, 255, 255), font=font)
    draw.text((360, 300), f"ID: {id}", fill=(255, 255, 255), font=font)
    if uname:
        draw.text((360, 350), f"USERNAME: @{uname}", fill=(255, 255, 255), font=font)

    pfp_position = (30, 150)
    background.paste(pfp, pfp_position, pfp)

    out_path = f"downloads/welcome#{id}.png"
    background.save(out_path)
    return out_path

@app.on_message(filters.command("welcome") & ~filters.private)
async def auto_state(_, message):
    usage = "**ᴜsᴀɢᴇ:**\n**⦿ /welcome [on|off]**"
    if len(message.command) == 1:
        return await message.reply_text(usage)

    chat_id = message.chat.id
    user = await app.get_chat_member(message.chat.id, message.from_user.id)

    if user.status not in (
        enums.ChatMemberStatus.ADMINISTRATOR,
        enums.ChatMemberStatus.OWNER,
    ):
        return await message.reply("**sᴏʀʀʏ ᴏɴʟʏ ᴀᴅᴍɪɴs ᴄᴀɴ ᴇɴᴀʙʟᴇ ᴡᴇʟᴄᴏᴍᴇ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ!**")

    is_disabled = await wlcm.find_one(chat_id)
    state = message.text.split(None, 1)[1].strip().lower()

    if state == "off":
        if is_disabled:
            await message.reply_text("**ᴡᴇʟᴄᴏᴍᴇ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ ᴀʟʀᴇᴀᴅʏ ᴅɪsᴀʙʟᴇᴅ !**")
        else:
            await wlcm.add_wlcm(chat_id)
            await message.reply_text(f"**ᴅɪsᴀʙʟᴇᴅ ᴡᴇʟᴄᴏᴍᴇ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ ɪɴ** {message.chat.title}")
    elif state == "on":
        if not is_disabled:
            await message.reply_text("**ᴡᴇʟᴄᴏᴍᴇ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ ᴀʟʀᴇᴀᴅʏ ᴇɴᴀʙʟᴇᴅ.**")
        else:
            await wlcm.rm_wlcm(chat_id)
            await message.reply_text(f"**ᴇɴᴀʙʟᴇᴅ ᴡᴇʟᴄᴏᴍᴇ ɴᴏᴛɪғɪᴄᴀᴛɪᴏɴ ɪɴ** {message.chat.title}")
    else:
        await message.reply_text(usage)

@app.on_chat_member_updated(filters.group, group=-3)
async def greet_new_member(_, member: ChatMemberUpdated):
    chat_id = member.chat.id

    if await wlcm.find_one(chat_id):
        return

    if not (member.new_chat_member and not member.old_chat_member):
        return
    if member.new_chat_member.status == "kicked":
        return

    user = member.new_chat_member.user
    count = await app.get_chat_members_count(chat_id)

    try:
        pic = await app.download_media(user.photo.big_file_id, file_name=f"pp{user.id}.png")
    except AttributeError:
        pic = "anony/assets/upic.png"

    old_msg = temp.MELCOW.get(f"welcome-{chat_id}")
    if old_msg is not None:
        try:
            await old_msg.delete()
        except Exception as e:
            LOGGER.error(e)

    try:
        welcomeimg = welcomepic(pic, user.first_name, member.chat.title, user.id, user.username)

        button_text = "๏ ᴠɪᴇᴡ ɴᴇᴡ ᴍᴇᴍʙᴇʀ ๏"
        add_button_text = "๏ ᴋɪᴅɴᴀᴘ ᴍᴇ ๏"
        deep_link = f"tg://openmessage?user_id={user.id}"
        add_link = f"https://t.me/{app.username}?startgroup=true"

        temp.MELCOW[f"welcome-{chat_id}"] = await app.send_photo(
            chat_id,
            photo=welcomeimg,
            caption=f"""
**❅────✦ ᴡᴇʟᴄᴏᴍᴇ ✦────❅**

▰▰▰▰▰▰▰▰▰▰▰▰▰
**➻ ɴᴀᴍᴇ »** {user.mention}
**➻ ɪᴅ »** `{user.id}`
**➻ ᴜ_ɴᴀᴍᴇ »** @{user.username if user.username else "N/A"}
**➻ ᴛᴏᴛᴀʟ ᴍᴇᴍʙᴇʀs »** {count}
▰▰▰▰▰▰▰▰▰▰▰▰▰

**❅─────✧❅✦❅✧─────❅**
""",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton(button_text, url=deep_link)],
                    [InlineKeyboardButton(text=add_button_text, url=add_link)],
                ]
            ),
        )
    except Exception as e:
        LOGGER.error(e)
