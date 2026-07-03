import os
import textwrap
from asyncio import gather
from traceback import format_exc

from PIL import Image, ImageDraw, ImageFont
from pyrogram import filters, raw
from pyrogram.errors import (
    PeerIdInvalid,
    ShortnameOccupyFailed,
    StickerEmojiInvalid,
    StickerPngDimensions,
    StickerPngNopng,
    UserIsBlocked,
)
from pyrogram.file_id import FileId
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from anony import app
from .er import capture_err
from .files import get_document_from_file_id, upload_document
from .st import (
    add_sticker_to_set,
    create_sticker,
    create_sticker_set,
    detect_sticker_type,
    get_sticker_set_by_name,
    remove_sticker_from_set,
)

MAX_STICKERS = 120
STATIC_TYPES  = {"jpeg", "jpg", "png", "webp", "bmp", "gif", "tiff", "tif", "ico"}
ANIMATED_TYPES = {"tgs"}
VIDEO_TYPES    = {"webm"}
ALL_TYPES      = STATIC_TYPES | ANIMATED_TYPES | VIDEO_TYPES

TMP = "/tmp"


def _cleanup(*paths):
    for p in paths:
        if p and os.path.isfile(p):
            os.remove(p)


def _to_png(src: str) -> str:
    dst = src.rsplit(".", 1)[0] + ".png"
    with Image.open(src) as img:
        img = img.convert("RGBA")
        w, h = img.size
        scale = 512 / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        img.save(dst, "PNG", optimize=True)
    return dst


async def _get_pack(client, uid, fname, bot_username, sticker):
    packname = f"f{uid}_by_{bot_username}"
    packnum  = 0
    for _ in range(50):
        stickerset = await get_sticker_set_by_name(client, packname)
        if not stickerset:
            await create_sticker_set(client, uid, f"{fname}'s kang pack", packname, [sticker])
            return packname
        if stickerset.set.count < MAX_STICKERS:
            try:
                await add_sticker_to_set(client, stickerset, sticker)
            except StickerEmojiInvalid:
                return None
            return packname
        packnum += 1
        packname = f"f{packnum}_{uid}_by_{bot_username}"
    return None



# ─── meme editor ──────────────────────────────────────────────────────────────

_meme_states: dict[str, dict] = {}

FONTS = {
    "Bold":       "https://cdn.jsdelivr.net/gh/google/fonts/ofl/oswald/Oswald%5Bwght%5D.ttf",
    "Sans":       "https://cdn.jsdelivr.net/gh/notofonts/notofonts.github.io/fonts/NotoSans/hinted/ttf/NotoSans-Bold.ttf",
    "Mono":       "https://cdn.jsdelivr.net/gh/notofonts/notofonts.github.io/fonts/NotoSansMono/hinted/ttf/NotoSansMono-Bold.ttf",
    "Serif":      "https://cdn.jsdelivr.net/gh/google/fonts/ofl/merriweather/Merriweather-Bold.ttf",
    "Condensed":  "https://cdn.jsdelivr.net/gh/google/fonts/ofl/barlow/Barlow-Bold.ttf",
}
FONT_NAMES = list(FONTS.keys())

SYSTEM_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/google-noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/google-noto-sans-fonts/NotoSans-Bold.ttf",
]

TEXT_COLORS = {
    "⚪ White":   (255, 255, 255, 255),
    "⚫ Black":   (0,   0,   0,   255),
    "🔴 Red":     (255, 60,  60,  255),
    "🟡 Yellow":  (255, 230, 0,   255),
    "🔵 Blue":    (80,  160, 255, 255),
    "🟢 Green":   (60,  220, 100, 255),
    "🟠 Orange":  (255, 140, 0,   255),
    "🟣 Purple":  (180, 80,  255, 255),
    "🩷 Pink":    (255, 105, 180, 255),
    "🩵 Cyan":    (0,   210, 230, 255),
}
COLOR_NAMES = list(TEXT_COLORS.keys())

OUTLINE_COLORS = {
    "⚫ Black":  (0,   0,   0,   255),
    "⚪ White":  (255, 255, 255, 255),
    "🔴 Red":    (200, 0,   0,   255),
    "🔵 Blue":   (0,   80,  200, 255),
    "None":      None,
}
OUTLINE_NAMES = list(OUTLINE_COLORS.keys())

POS_CYCLE = ["top", "bottom", "center", "top+bottom"]


def _font_cache_path(name: str) -> str:
    return f"{TMP}/meme_font_{name}.ttf"


def _ensure_font(name: str = "Bold") -> str:
    path = _font_cache_path(name)
    if os.path.isfile(path) and os.path.getsize(path) > 1000:
        return path

    import glob
    for sys_font in SYSTEM_FONTS:
        if os.path.isfile(sys_font):
            import shutil; shutil.copy(sys_font, path)
            return path

    found = glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)
    if found:
        import shutil; shutil.copy(found[0], path)
        return path

    import subprocess, glob as g
    for cmd in [["yum","-y","install","google-noto-sans-fonts"],
                ["dnf","-y","install","google-noto-sans-fonts"],
                ["apt-get","-y","install","fonts-dejavu-core"]]:
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
            found = g.glob("/usr/share/fonts/**/*.ttf", recursive=True)
            if found:
                import shutil; shutil.copy(found[0], path)
                return path
        except Exception:
            continue

    import urllib.request
    for url in [FONTS.get(name, ""), *FONTS.values()]:
        if not url:
            continue
        try:
            urllib.request.urlretrieve(url, path)
            if os.path.isfile(path) and os.path.getsize(path) > 1000:
                return path
        except Exception:
            continue

    raise RuntimeError("no font available. run: sudo yum install -y google-noto-sans-fonts")


def _make_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_ensure_font(name), size)


def _auto_fit(text: str, font_name: str, max_w: int, start_size: int) -> ImageFont.FreeTypeFont:
    size = start_size
    while size > 8:
        fnt  = _make_font(font_name, size)
        bbox = fnt.getbbox(text)
        if (bbox[2] - bbox[0]) <= max_w:
            return fnt
        size -= 2
    return _make_font(font_name, 8)


def _draw_text(draw: ImageDraw.ImageDraw, text: str, x: int, y: int,
               fnt: ImageFont.FreeTypeFont, fill: tuple, outline,
               shadow: bool, opacity: int):
    actual_fill = fill[:3] + (opacity,)

    if shadow:
        shadow_color = (0, 0, 0, max(0, opacity - 80))
        draw.text((x + 4, y + 4), text, font=fnt, fill=shadow_color)

    if outline is not None:
        outline_c = outline[:3] + (opacity,)
        for ox, oy in [(-3,0),(3,0),(0,-3),(0,3),(-2,-2),(2,-2),(-2,2),(2,2)]:
            draw.text((x + ox, y + oy), text, font=fnt, fill=outline_c)

    draw.text((x, y), text, font=fnt, fill=actual_fill)


def _render_meme(orig_path: str, state: dict) -> Image.Image:
    with Image.open(orig_path) as base:
        img = base.convert("RGBA")

    w, h = img.size

    if state["bg_blur"]:
        from PIL import ImageFilter
        img = img.filter(ImageFilter.GaussianBlur(radius=state["bg_blur"]))

    if state["rotation"]:
        img = img.rotate(-state["rotation"], expand=False, resample=Image.Resampling.BICUBIC)
        w, h = img.size

    draw      = ImageDraw.Draw(img, "RGBA")
    pad       = 12
    color     = TEXT_COLORS[COLOR_NAMES[state["color_idx"]]]
    outline   = OUTLINE_COLORS[OUTLINE_NAMES[state["outline_idx"]]]
    font_name = FONT_NAMES[state["font_idx"]]
    size      = state["font_size"]
    shadow    = state["shadow"]
    opacity   = int(state["opacity"] * 2.55)
    pos       = POS_CYCLE[state["pos_idx"]]

    def _block(text: str, anchor_top: bool, center: bool = False):
        fnt  = _auto_fit(text, font_name, w - pad * 2, size)
        bbox = fnt.getbbox(text)
        tw   = bbox[2] - bbox[0]
        th   = bbox[3] - bbox[1]
        x    = (w - tw) // 2
        if center:
            y = (h - th) // 2
        elif anchor_top:
            y = pad
        else:
            y = h - th - pad * 2

        if state["text_bg"]:
            margin = 6
            bg_color = (0, 0, 0, 140)
            draw.rectangle((x - margin, y - margin, x + tw + margin, y + th + margin), fill=bg_color)

        _draw_text(draw, text, x, y, fnt, color, outline, shadow, opacity)

    top    = state["top"]
    bottom = state["bottom"]

    if pos == "top" and top:
        _block(top, anchor_top=True)
    elif pos == "bottom" and bottom:
        _block(bottom, anchor_top=False)
    elif pos == "center":
        text = top or bottom
        if text:
            _block(text, anchor_top=False, center=True)
    elif pos == "top+bottom":
        if top:
            _block(top, anchor_top=True)
        if bottom:
            _block(bottom, anchor_top=False)

    return img


def _state_summary(state: dict) -> str:
    pos       = POS_CYCLE[state["pos_idx"]]
    color     = COLOR_NAMES[state["color_idx"]]
    outline   = OUTLINE_NAMES[state["outline_idx"]]
    font_name = FONT_NAMES[state["font_idx"]]
    extras    = []
    if state["shadow"]:   extras.append("shadow")
    if state["text_bg"]:  extras.append("bg")
    if state["bg_blur"]:  extras.append(f"blur:{state['bg_blur']}")
    extra_str = "  " + " · ".join(extras) if extras else ""
    return (
        f"📝 `{state['top'] or '—'}` / `{state['bottom'] or '—'}`\n"
        f"🎨 {color}  🖊 {outline}  🔠 {font_name}  📏 {state['font_size']}px\n"
        f"📍 {pos}  🔄 {state['rotation']}°  👁 {state['opacity']}%{extra_str}"
    )


def _panel(key: str, state: dict, uid: int) -> InlineKeyboardMarkup:
    k  = f"{uid}:{key}"
    c  = COLOR_NAMES[state["color_idx"]]
    o  = OUTLINE_NAMES[state["outline_idx"]]
    fn = FONT_NAMES[state["font_idx"]]
    sz = state["font_size"]
    ro = state["rotation"]
    op = state["opacity"]
    bg = "✅ BG" if state["text_bg"] else "☐ BG"
    sh = "✅ Shadow" if state["shadow"] else "☐ Shadow"
    pos = POS_CYCLE[state["pos_idx"]]
    blur = state["bg_blur"]

    def b(label, action):
        return InlineKeyboardButton(label, callback_data=f"me:{action}:{k}")

    return InlineKeyboardMarkup([
        # color + outline
        [b(f"🎨 {c}", "color"),    b(f"🖊 {o}", "outline")],
        # font + position
        [b(f"🔠 {fn}", "font"),    b(f"📍 {pos}", "pos")],
        # size
        [b("➖", "szdown"), b(f"📏 {sz}px", "noop"), b("➕", "szup")],
        # rotation
        [b("↺ -15°", "rotl"), b(f"🔄 {ro}°", "noop"), b("↻ +15°", "rotr")],
        # opacity
        [b("🌑 -10%", "opdown"), b(f"👁 {op}%", "noop"), b("☀️ +10%", "opup")],
        # blur + extras
        [b("🌀 -blur", "blurdown"), b(f"🌫 blur:{blur}", "noop"), b("🌀 +blur", "blurup")],
        # toggles
        [b(bg, "textbg"), b(sh, "shadow")],
        # done / kang / discard
        [b("✅ Save as Sticker", "done"), b("🎒 Kang It", "kang"), b("🗑 Discard", "discard")],
    ])


async def _upload_sticker(client, chat_id: int, img: Image.Image, emoji: str = "🤔"):
    img = img.convert("RGBA")
    w, h = img.size
    if max(w, h) != 512:
        scale = 512 / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    path = f"{TMP}/sticker_upload_{chat_id}.webp"
    img.save(path, "WEBP", lossless=True, quality=100, method=6)
    try:
        media = await client.invoke(
            raw.functions.messages.UploadMedia(
                peer=await client.resolve_peer(chat_id),
                media=raw.types.InputMediaUploadedDocument(
                    mime_type="image/webp",
                    file=await client.save_file(path),
                    attributes=[
                        raw.types.DocumentAttributeFilename(file_name="sticker.webp"),
                        raw.types.DocumentAttributeSticker(
                            alt=emoji,
                            stickerset=raw.types.InputStickerSetEmpty(),
                        ),
                    ],
                ),
            )
        )
        doc = media.document
        await client.invoke(
            raw.functions.messages.SendMedia(
                peer=await client.resolve_peer(chat_id),
                media=raw.types.InputMediaDocument(
                    id=raw.types.InputDocument(
                        id=doc.id,
                        access_hash=doc.access_hash,
                        file_reference=doc.file_reference,
                    )
                ),
                message="",
                random_id=client.rnd_id(),
            )
        )
    finally:
        _cleanup(path)


@app.on_message(filters.command("meme"))
@capture_err
async def meme(client, message: Message):
    r = message.reply_to_message
    if not r or not r.sticker:
        return await message.reply("reply to a sticker.\nusage: /meme top text | bottom text")
    if r.sticker.is_animated or r.sticker.is_video:
        return await message.reply("only static stickers are supported.")

    raw_text = " ".join(message.text.split()[1:])
    if not raw_text:
        return await message.reply("usage: /meme top text | bottom text")

    parts  = raw_text.split("|", 1)
    top    = parts[0].strip()
    bottom = parts[1].strip() if len(parts) == 2 else ""
    if not top and not bottom:
        return await message.reply("provide at least top or bottom text.")

    m   = await message.reply("generating meme sticker...")
    tmp = None
    try:
        tmp = await app.download_media(r.sticker)
        uid = message.from_user.id
        state = {
            "orig":        tmp,
            "top":         top,
            "bottom":      bottom,
            "color_idx":   0,
            "outline_idx": 0,
            "font_idx":    0,
            "font_size":   80,
            "rotation":    0,
            "opacity":     100,
            "shadow":      False,
            "text_bg":     False,
            "bg_blur":     0,
            "pos_idx":     3 if (top and bottom) else (0 if top else 1),
            "emoji":       r.sticker.emoji or "🤔",
            "chat_id":     message.chat.id,
            "owner":       uid,
        }
        out = _render_meme(tmp, state)
        await _upload_sticker(client, message.chat.id, out, state["emoji"])

        state_key = f"{message.chat.id}:{m.id}"
        _meme_states[state_key] = state

        await m.edit(
            _state_summary(state),
            reply_markup=_panel(state_key, state, uid),
        )
    except Exception as e:
        await m.edit(f"error: {e}")
        print(format_exc())
        _cleanup(tmp)


@app.on_callback_query(filters.regex(r"^me:"))
@capture_err
async def meme_editor(client, query: CallbackQuery):
    _, action, uid_str, chat_id_str, msg_id_str = query.data.split(":", 4)
    uid       = int(uid_str)
    state_key = f"{chat_id_str}:{msg_id_str}"
    state     = _meme_states.get(state_key)

    if query.from_user.id != uid:
        return await query.answer("this is not your meme editor.", show_alert=True)

    if not state:
        return await query.answer("session expired. use /meme again.", show_alert=True)

    if action == "noop":
        return await query.answer()

    if action == "discard":
        _cleanup(state.get("orig"))
        _meme_states.pop(state_key, None)
        await query.message.delete()
        return await query.answer("discarded.")

    if action == "done":
        try:
            out = _render_meme(state["orig"], state)
            await _upload_sticker(client, state["chat_id"], out, state["emoji"])
        except Exception as e:
            return await query.answer(f"error: {e}", show_alert=True)
        _cleanup(state.get("orig"))
        _meme_states.pop(state_key, None)
        await query.message.delete()
        return await query.answer("sticker saved!")

    if action == "kang":
        await query.answer("kanging your meme sticker...")
        try:
            out         = _render_meme(state["orig"], state)
            user        = query.from_user
            bot_me      = await client.get_me()
            bot_username = bot_me.username
            fname       = (user.first_name or "User")[:32]

            import io
            buf = io.BytesIO()
            img = out.convert("RGBA")
            w, h = img.size
            if max(w, h) != 512:
                scale = 512 / max(w, h)
                img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
            img.save(buf, "WEBP", lossless=True, quality=100, method=6)
            buf.seek(0)

            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as tmp:
                tmp.write(buf.read())
                tmp_path = tmp.name

            try:
                doc     = await upload_document(client, tmp_path, state["chat_id"])
                sticker = await create_sticker(doc, state["emoji"])
                packname = await _get_pack(client, uid, fname, bot_username, sticker)
            finally:
                _cleanup(tmp_path)

            if not packname:
                return await query.message.reply("failed to kang: invalid emoji or too many packs.")

            _cleanup(state.get("orig"))
            _meme_states.pop(state_key, None)
            await query.message.edit(
                "meme sticker kanged to your pack!",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("View Pack", url=f"https://t.me/addstickers/{packname}")
                ]])
            )
        except Exception as e:
            await query.message.reply(f"kang error: {e}")
            print(format_exc())
        return

    if action == "color":
        state["color_idx"] = (state["color_idx"] + 1) % len(COLOR_NAMES)
    elif action == "outline":
        state["outline_idx"] = (state["outline_idx"] + 1) % len(OUTLINE_NAMES)
    elif action == "font":
        next_idx = (state["font_idx"] + 1) % len(FONT_NAMES)
        try:
            _ensure_font(FONT_NAMES[next_idx])
            state["font_idx"] = next_idx
        except Exception:
            return await query.answer("font download failed.", show_alert=True)
    elif action == "pos":
        state["pos_idx"] = (state["pos_idx"] + 1) % len(POS_CYCLE)
    elif action == "szup":
        state["font_size"] = min(state["font_size"] + 6, 220)
    elif action == "szdown":
        state["font_size"] = max(state["font_size"] - 6, 10)
    elif action == "rotr":
        state["rotation"] = (state["rotation"] + 15) % 360
    elif action == "rotl":
        state["rotation"] = (state["rotation"] - 15) % 360
    elif action == "opup":
        state["opacity"] = min(state["opacity"] + 10, 100)
    elif action == "opdown":
        state["opacity"] = max(state["opacity"] - 10, 10)
    elif action == "blurup":
        state["bg_blur"] = min(state["bg_blur"] + 1, 10)
    elif action == "blurdown":
        state["bg_blur"] = max(state["bg_blur"] - 1, 0)
    elif action == "shadow":
        state["shadow"] = not state["shadow"]
    elif action == "textbg":
        state["text_bg"] = not state["text_bg"]

    try:
        out = _render_meme(state["orig"], state)
        await _upload_sticker(client, state["chat_id"], out, state["emoji"])
        await query.message.edit(
            _state_summary(state),
            reply_markup=_panel(state_key, state, uid),
        )
        await query.answer()
    except Exception as e:
        await query.answer(f"error: {e}", show_alert=True)
        print(format_exc())


@app.on_message(filters.command("get_sticker"))
@capture_err
async def get_sticker(_, message: Message):
    r = message.reply_to_message
    if not r or not r.sticker:
        return await message.reply("reply to a sticker.")
    m = await message.reply("sending...")
    f = await r.download(f"{r.sticker.file_unique_id}.png")
    from asyncio import gather
    await gather(message.reply_photo(f), message.reply_document(f))
    await m.delete()
    _cleanup(f)


@app.on_message(filters.command("stickerinfo"))
@capture_err
async def sticker_info(_, message: Message):
    r = message.reply_to_message
    if not r or not r.sticker:
        return await message.reply("reply to a sticker.")
    s    = r.sticker
    kind = "animated" if s.is_animated else "video" if s.is_video else "static"
    await message.reply(
        f"file id: `{s.file_id}`\n"
        f"emoji: {s.emoji or 'none'}\n"
        f"type: {kind}\n"
        f"set: `{s.set_name or 'none'}`\n"
        f"size: {s.file_size} bytes\n"
        f"dimensions: {s.width}x{s.height}"
    )


@app.on_message(filters.command("delsticker"))
@capture_err
async def del_sticker(client, message: Message):
    r = message.reply_to_message
    if not r or not r.sticker:
        return await message.reply("reply to a sticker to delete it from its pack.")
    m = await message.reply("deleting...")
    try:
        decoded = FileId.decode(r.sticker.file_id)
        doc = raw.types.InputDocument(
            id=decoded.media_id,
            access_hash=decoded.access_hash,
            file_reference=decoded.file_reference,
        )
        await remove_sticker_from_set(client, doc)
        await m.edit("sticker deleted from pack.")
    except Exception as e:
        await m.edit(f"failed: {e}")


@app.on_message(filters.command("kang"))
@capture_err
async def kang(client, message: Message):
    if not message.reply_to_message:
        return await message.reply("reply to a sticker or image to kang.")
    if not message.from_user:
        return await message.reply("anon admin, kang stickers in my pm.")

    m       = await message.reply("kanging...")
    args    = message.text.split()
    replied = message.reply_to_message
    emoji   = args[1] if len(args) > 1 else (
        replied.sticker.emoji if replied.sticker and replied.sticker.emoji else "🤔"
    )

    tmp = None
    try:
        if replied.sticker:
            sticker = await create_sticker(
                await get_document_from_file_id(replied.sticker.file_id), emoji
            )
        elif doc := (replied.photo or replied.document):
            if doc.file_size and doc.file_size > 10_000_000:
                return await m.edit("file size too large (max 10MB).")
            tmp = await app.download_media(doc)
            if not tmp or not os.path.exists(tmp):
                return await m.edit("failed to download file.")
            ext = tmp.rsplit(".", 1)[-1].lower()
            if ext not in ALL_TYPES:
                _cleanup(tmp)
                return await m.edit(
                    f"format not supported.\nstatic: {', '.join(sorted(STATIC_TYPES))}\n"
                    f"animated: tgs | video: webm"
                )
            animated, video = detect_sticker_type(tmp)
            if not animated and not video and ext != "png":
                png = _to_png(tmp)
                if png != tmp:
                    _cleanup(tmp)
                tmp = png
            sticker = await create_sticker(
                await upload_document(client, tmp, message.chat.id), emoji
            )
            _cleanup(tmp)
            tmp = None
        else:
            return await m.edit("cannot kang this message type.")

    except ShortnameOccupyFailed:
        _cleanup(tmp)
        return await m.edit("change your name or username and try again.")
    except Exception as e:
        _cleanup(tmp)
        await m.edit(f"error: {e}")
        print(format_exc())
        return

    uid          = message.from_user.id
    fname        = message.from_user.first_name[:32]
    bot_username = (await client.get_me()).username

    try:
        packname = await _get_pack(client, uid, fname, bot_username, sticker)
        if not packname:
            return await m.edit("invalid emoji or too many packs.")
        await m.edit(
            "sticker kanged!\ntap below to open your pack",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("View Pack", url=f"https://t.me/addstickers/{packname}")
            ]])
        )
    except (PeerIdInvalid, UserIsBlocked):
        await m.edit(
            "start a private chat with me first!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Start Bot", url=f"https://t.me/{bot_username}")
            ]])
        )
    except StickerPngNopng:
        await m.edit("sticker must be a png file.")
    except StickerPngDimensions:
        await m.edit("invalid sticker dimensions.")
    except Exception as e:
        await m.edit(f"unexpected error: {e}")
        print(format_exc())