from typing import List, Optional

from pyrogram import Client, errors, raw


async def get_sticker_set_by_name(client: Client, name: str) -> Optional[raw.types.messages.StickerSet]:
    try:
        return await client.invoke(
            raw.functions.messages.GetStickerSet(
                stickerset=raw.types.InputStickerSetShortName(short_name=name),
                hash=0,
            )
        )
    except errors.StickersetInvalid:
        return None


async def create_sticker_set(
    client: Client,
    owner: int,
    title: str,
    short_name: str,
    stickers: List[raw.types.InputStickerSetItem],
) -> raw.types.messages.StickerSet:
    return await client.invoke(
        raw.functions.stickers.CreateStickerSet(
            user_id=await client.resolve_peer(owner),
            title=title,
            short_name=short_name,
            stickers=stickers,
        )
    )


async def add_sticker_to_set(
    client: Client,
    stickerset: raw.types.messages.StickerSet,
    sticker: raw.types.InputStickerSetItem,
) -> raw.types.messages.StickerSet:
    return await client.invoke(
        raw.functions.stickers.AddStickerToSet(
            stickerset=raw.types.InputStickerSetShortName(short_name=stickerset.set.short_name),
            sticker=sticker,
        )
    )


async def remove_sticker_from_set(
    client: Client,
    sticker: raw.types.InputDocument,
) -> raw.types.messages.StickerSet:
    return await client.invoke(
        raw.functions.stickers.RemoveStickerFromSet(sticker=sticker)
    )


async def create_sticker(
    document: raw.types.InputDocument,
    emoji: str,
) -> raw.types.InputStickerSetItem:
    return raw.types.InputStickerSetItem(document=document, emoji=emoji)


def detect_sticker_type(filename: str) -> tuple[bool, bool]:
    ext = filename.rsplit(".", 1)[-1].lower()
    return ext == "tgs", ext == "webm"
