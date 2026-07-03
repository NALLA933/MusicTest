import sys
import traceback
from functools import wraps

from pyrogram.errors.exceptions.forbidden_403 import ChatWriteForbidden
from anony import app

LOGGER = -1002059929123


def split_limits(text):
    if len(text) < 2048:
        return [text]
    lines = text.splitlines(True)
    small_msg = ""
    result = []
    for line in lines:
        if len(small_msg) + len(line) < 2048:
            small_msg += line
        else:
            result.append(small_msg)
            small_msg = line
    result.append(small_msg)
    return result


def capture_err(func):
    @wraps(func)
    async def capture(client, message, *args, **kwargs):
        try:
            return await func(client, message, *args, **kwargs)
        except ChatWriteForbidden:
            await app.leave_chat(message.chat.id)
        except Exception as err:
            errors = "".join(traceback.format_exception(*sys.exc_info()))
            log = "**ERROR** | `{}` | `{}`\n\n```{}```\n\n```{}```\n".format(
                0 if not message.from_user else message.from_user.id,
                0 if not message.chat else message.chat.id,
                message.text or message.caption,
                errors,
            )
            for chunk in split_limits(log):
                await app.send_message(LOGGER, chunk)
            raise err

    return capture