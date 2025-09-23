import io
import uuid
from typing import Any

import bprint
from telegram import Message, User
from telegram.constants import ChatAction, MessageLimit

MESSAGE_CHAR_LIMIT = MessageLimit.MAX_TEXT_LENGTH
TRUNCATION_SUFFIX = "... (truncated)"
SKIP_ATTR_NAMES = (
    "CONSTRUCTOR_ID",
    "SUBCLASS_OF_ID",
    "access_hash",
    "message",
    "raw_text",
    "phone",
)
SKIP_ATTR_VALUES = (False,)
SKIP_ATTR_TYPES = ()


def mention_user(user: User) -> str:
    if user.username:
        name = f"@{user.username}"
    elif user.first_name and user.last_name:
        name = f"{user.first_name} {user.last_name}"
    elif user.first_name:
        name = user.first_name
    else:
        name = "Deleted Account"

    return f"[{name}](tg://user?id={user.id})"


def filter_code_block(inp: str) -> str:
    if inp.startswith("```") and inp.endswith("```"):
        inner = inp[3:-3]
        if inner.startswith("\n"):
            inner = inner[1:]
        else:
            parts = inner.split("\n", 1)
            inner = parts[1] if len(parts) > 1 else ""

        return inner

    if inp.startswith("`") and inp.endswith("`"):
        return inp[1:-1]

    return inp


def _bprint_skip_predicate(name: str, value: Any) -> bool:
    return (
        name.startswith("_")
        or value is None
        or callable(value)
        or (name in SKIP_ATTR_NAMES)
        or (value in SKIP_ATTR_VALUES)
        or (type(value) in SKIP_ATTR_TYPES)
    )


def pretty_print_entity(entity: Any) -> str:
    return bprint.bprint(entity, stream=str, skip_predicate=_bprint_skip_predicate)


def truncate(text: str) -> str:
    suffix = TRUNCATION_SUFFIX
    if text.endswith("```"):
        suffix += "```"

    if len(text) > MESSAGE_CHAR_LIMIT:
        return text[: MESSAGE_CHAR_LIMIT - len(suffix)] + suffix

    return text


async def send_as_document(content: str, msg: Message, caption: str) -> Message:
    with io.BytesIO(str(content).encode()) as o:
        o.name = f"{str(uuid.uuid4()).split('-')[0].upper()}.TXT"
        return await msg.reply_document(document=o, caption=f"❯ ```{caption}```")


async def _send_action(msg: Message, timeout: float = 1.0, **kwargs: Any) -> None:
    action = ChatAction.TYPING
    if "photo" in kwargs:
        action = ChatAction.UPLOAD_PHOTO
    elif "video" in kwargs:
        action = ChatAction.UPLOAD_VIDEO
    elif "animation" in kwargs:
        action = ChatAction.UPLOAD_DOCUMENT
    elif "document" in kwargs:
        action = ChatAction.UPLOAD_DOCUMENT
    elif "audio" in kwargs:
        action = ChatAction.UPLOAD_AUDIO
    elif "voice" in kwargs:
        action = ChatAction.UPLOAD_VOICE

    try:
        bot = msg._bot
        await bot.send_chat_action(
            chat_id=msg.chat_id,
            action=action,
            read_timeout=timeout,
            write_timeout=timeout,
            connect_timeout=timeout,
            pool_timeout=timeout,
        )
    except Exception:
        pass
