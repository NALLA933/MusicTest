import asyncio
import io
import uuid
from html import escape

from anony import app
from pyrogram import enums, filters, types


@app.on_message(filters.command(["sh", "shell"]) & filters.user(app.owner))
@app.on_edited_message(filters.command(["sh", "shell"]) & filters.user(app.owner))
async def shell_handler(_, message: types.Message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: /sh <command>")

    cmd = message.text.split(None, 1)[1]

    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode(errors="replace").strip() or "(no output)"
    response = f"<code>{escape(cmd)}</code>\n\n<pre>{escape(output)}</pre>"

    if len(response) > 4096:
        with io.BytesIO(output.encode()) as f:
            f.name = f"{uuid.uuid4().hex[:8]}.txt"
            return await message.reply_document(f)

    await message.reply_text(response, parse_mode=enums.ParseMode.HTML)