import os

from PIL import Image, ImageOps
from pyrogram import Client, raw
from pyrogram.file_id import FileId

MAX_SIZE = 512


def _resize_image(img: Image.Image) -> Image.Image:
    img = img.convert("RGBA")
    img.thumbnail((MAX_SIZE, MAX_SIZE), Image.Resampling.LANCZOS)
    if max(img.size) < MAX_SIZE:
        scale = MAX_SIZE / max(img.size)
        img = img.resize(
            (int(img.width * scale), int(img.height * scale)),
            Image.Resampling.LANCZOS,
        )
    return img


async def resize_file_to_sticker_size(file_path: str) -> str:
    with Image.open(file_path) as img:
        resized = _resize_image(img)

    os.remove(file_path)
    out_path = file_path.rsplit(".", 1)[0] + ".png"
    resized.save(out_path, "PNG", optimize=True)
    return out_path


async def upload_document(client: Client, file_path: str, chat_id: int) -> raw.types.InputDocument:
    media = await client.invoke(
        raw.functions.messages.UploadMedia(
            peer=await client.resolve_peer(chat_id),
            media=raw.types.InputMediaUploadedDocument(
                mime_type=client.guess_mime_type(file_path) or "application/zip",
                file=await client.save_file(file_path),
                attributes=[
                    raw.types.DocumentAttributeFilename(file_name=os.path.basename(file_path))
                ],
                force_file=False,
            ),
        )
    )
    doc = media.document
    return raw.types.InputDocument(
        id=doc.id,
        access_hash=doc.access_hash,
        file_reference=doc.file_reference,
    )


async def get_document_from_file_id(file_id: str) -> raw.types.InputDocument:
    decoded = FileId.decode(file_id)
    return raw.types.InputDocument(
        id=decoded.media_id,
        access_hash=decoded.access_hash,
        file_reference=decoded.file_reference,
    )