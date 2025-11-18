from typing import Iterable, List, Optional, Union

from telegram import (
    ChatAdministratorRights,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    ReplyKeyboardMarkup,
)


class KeyboardBuilder:
    def __init__(self):
        self._rows: List[List[InlineKeyboardButton]] = []

    def add_row(
        self, *buttons: Union[InlineKeyboardButton, tuple]
    ) -> "KeyboardBuilder":
        row = []
        for b in buttons:
            if isinstance(b, InlineKeyboardButton):
                row.append(b)
            elif isinstance(b, tuple):
                text, cb = b if len(b) == 2 else (b[0], None)
                row.append(InlineKeyboardButton(text, callback_data=cb))

        self._rows.append(row)
        return self

    def add_button(
        self, text: str, callback_data: Optional[str] = None, url: Optional[str] = None
    ) -> "KeyboardBuilder":
        self._rows.append(
            [InlineKeyboardButton(text, callback_data=callback_data, url=url)]
        )
        return self

    def add_back(
        self, text: str = "⬅️ Back", callback_data: str = "back"
    ) -> "KeyboardBuilder":
        self._rows.append([InlineKeyboardButton(text, callback_data=callback_data)])
        return self

    def build(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(self._rows)


# --------------------------
# Reusable keyboard helpers
# --------------------------


def settings_menu() -> InlineKeyboardMarkup:
    return (
        KeyboardBuilder()
        .add_button("Chat", "settings:chat")
        .add_button("Bot Settings", "settings:bot")
        .build()
    )


def bot_menu() -> InlineKeyboardMarkup:
    return (
        KeyboardBuilder()
        .add_button("Set Welcome", "bot:set")
        .add_button("Preview Welcome", "bot:show")
        .add_button("Clear Welcome", "bot:clear")
        .add_back(callback_data="bot:back")
        .build()
    )


def chat_menu() -> InlineKeyboardMarkup:
    return (
        KeyboardBuilder()
        .add_row(("Tambahkan Chat", "chat:add"), ("Hapus Chat", "chat:del"))
        .add_row(("Edit Chat", "chat:edit"), ("List Chat", "chat:list"))
        .add_back(callback_data="settings:back")
        .build()
    )


def wizard_controls(
    *, skip: bool = False, cancel: bool = False
) -> InlineKeyboardMarkup:
    row = []
    if skip:
        row.append(InlineKeyboardButton("⏭️ Skip", callback_data="wiz:skip"))

    if cancel:
        row.append(InlineKeyboardButton("✖️ Cancel", callback_data="wiz:cancel"))

    return InlineKeyboardMarkup([row] if row else [])


def pick_list(
    rows: Iterable[dict], prefix: str, icon: str, back: str
) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    for row in rows:
        title = row.get("title") or "Unknown"
        chat_id = row.get("chat_id")
        label = f"{icon} {title[:18]} | {chat_id}"
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"{prefix}:{chat_id}")]
        )

    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data=back)])
    return InlineKeyboardMarkup(buttons)


def confirm_delete(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Hapus", callback_data=f"delconfirm:{chat_id}"),
                InlineKeyboardButton("↩️ Batal", callback_data="delcancel"),
            ],
            [InlineKeyboardButton("⬅️ Back", callback_data="del:back")],
        ]
    )


def request_chat_keyboard(uid: int) -> ReplyKeyboardMarkup:
    rights = ChatAdministratorRights(
        is_anonymous=False,
        can_manage_chat=False,
        can_delete_messages=False,
        can_manage_video_chats=False,
        can_restrict_members=False,
        can_promote_members=False,
        can_change_info=False,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
        can_invite_users=True,
    )

    gid = (uid * 10 + 1) % (2**31 - 1)
    cid = (uid * 10 + 2) % (2**31 - 1)

    group_btn = KeyboardButton(
        text="➕ Group",
        request_chat=KeyboardButtonRequestChat(
            request_id=gid,
            chat_is_channel=False,
            bot_is_member=True,
            user_administrator_rights=rights,
            bot_administrator_rights=rights,
        ),
    )
    channel_btn = KeyboardButton(
        text="➕ Channel",
        request_chat=KeyboardButtonRequestChat(
            request_id=cid,
            chat_is_channel=True,
            bot_is_member=True,
            user_administrator_rights=rights,
            bot_administrator_rights=rights,
        ),
    )
    cancel_btn = KeyboardButton(text="✖️ Cancel")

    return ReplyKeyboardMarkup(
        [[group_btn, channel_btn], [cancel_btn]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
