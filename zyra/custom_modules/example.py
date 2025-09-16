"""Example module demonstrating interactive callback button functionality.

This module serves as a comprehensive example of how to use Telegram's
Inline Keyboards and handle the resulting callback queries within the Zyra bot
framework. It includes commands to generate interactive menus and counters,
and a robust system for processing user button clicks.

Note: This module is disabled by default (`disabled = True`) and is intended
to be used as a reference or template for creating new interactive modules.
"""

from typing import ClassVar

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from .. import listener, module


class CallbackHandler(module.Module):
    """Handles commands for interactive menus and counters with callback buttons.

    This module provides examples for handling various user interactions through
    inline keyboards, such as displaying system status, user info, random numbers,
    and updating a counter. It is triggered by the `/menu` and `/counter` commands.
    """

    name: ClassVar[str] = "callback"
    disabled: ClassVar[bool] = True

    @listener.on_commands("menu", "buttons")
    @listener.desc("Show interactive menu with buttons")
    @listener.usage("menu - Display interactive button menu")
    async def show_menu(self, ctx: listener.Context) -> None:
        """Responds to the /menu command by showing a main menu with callback buttons.

        Args:
            ctx: The command context provided by the listener.
        """
        keyboard = [
            [
                InlineKeyboardButton("📊 Status", callback_data="status"),
                InlineKeyboardButton("ℹ️ Info", callback_data="info"),
            ],
            [
                InlineKeyboardButton("🎲 Random", callback_data="random"),
                InlineKeyboardButton("⏰ Time", callback_data="time"),
            ],
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
                InlineKeyboardButton("❌ Close", callback_data="close"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        menu_text = "🎛️ <b>Interactive Menu</b>\n\n" "Choose an option below:"

        await ctx.respond(menu_text, reply_markup=reply_markup)

    @listener.on_commands("counter")
    @listener.desc("Show counter with increment/decrement buttons")
    @listener.usage("counter [start_number] - Start a counter (default: 0)")
    async def show_counter(self, ctx: listener.Context) -> None:
        """Responds to the /counter command with an interactive counter.

        An optional starting number can be provided as an argument.

        Args:
            ctx: The command context provided by the listener.
        """
        # Get starting number from args
        start_num = 0
        if ctx.args and ctx.args[0].isdigit():
            start_num = int(ctx.args[0])

        keyboard = [
            [
                InlineKeyboardButton("➖", callback_data=f"counter_dec_{start_num}"),
                InlineKeyboardButton("🔄", callback_data=f"counter_reset_{start_num}"),
                InlineKeyboardButton("➕", callback_data=f"counter_inc_{start_num}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        counter_text = (
            f"🔢 <b>Counter</b>\n\n" f"Current value: <code>{start_num}</code>"
        )

        await ctx.respond(counter_text, reply_markup=reply_markup)

    @listener.on_callback_query()
    async def handle_callback(self, ctx: listener.Context) -> None:
        """Acts as a central dispatcher for incoming callback queries.

        This function reads the `callback_data` from a query and routes it to the
        appropriate private handler method. It always answers the query first to
        remove the "loading" state on the user's client.

        Args:
            ctx: The context containing the callback query.
        """
        query = ctx.update.callback_query
        if not query or not query.data:
            return

        await query.answer()  # Always answer the callback query

        data = query.data

        # Route callback data to the appropriate handler.
        # The 'back_to_menu' action is handled by a separate, dedicated listener.
        if data == "back_to_menu":
            return
        elif data == "status":
            await self._handle_status(query)
        elif data == "info":
            await self._handle_info(query)
        elif data == "random":
            await self._handle_random(query)
        elif data == "time":
            await self._handle_time(query)
        elif data == "refresh":
            await self._handle_refresh(query)
        elif data == "close":
            await self._handle_close(query)
        elif data.startswith("counter_"):
            await self._handle_counter(query, data)
        else:
            await query.edit_message_text("❌ Unknown callback action!")

    async def _handle_status(self, query: CallbackQuery) -> None:
        """Handles the 'status' callback by displaying system stats.

        Args:
            query: The `CallbackQuery` object from the event.
        """
        import platform

        try:
            import psutil

            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            status_text = (
                f"📊 <b>System Status</b>\n\n"
                f"🖥️ CPU: <code>{cpu_percent}%</code>\n"
                f"💾 RAM: <code>{memory.percent}%</code>\n"
                f"💿 Disk: <code>{disk.percent}%</code>\n"
                f"🐧 OS: <code>{platform.system()}</code>\n"
                f"🔄 Python: <code>{platform.python_version()}</code>"
            )
        except ImportError:
            status_text = (
                f"📊 <b>Bot Status</b>\n\n"
                f"✅ Bot is running\n"
                f"🔄 Python: <code>{platform.python_version()}</code>\n"
                f"🐧 OS: <code>{platform.system()}</code>"
            )

        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(status_text, reply_markup=reply_markup)

    async def _handle_info(self, query: CallbackQuery) -> None:
        """Handles the 'info' callback by displaying user and chat info.

        Args:
            query: The `CallbackQuery` object from the event.
        """
        user = query.from_user
        chat = query.message.chat if query.message else None

        info_text = (
            f"ℹ️ <b>Information</b>\n\n"
            f"👤 User: <code>{user.first_name if user else 'Unknown'}</code>\n"
            f"🆔 User ID: <code>{user.id if user else 'N/A'}</code>\n"
            f"💬 Chat: <code>{chat.title or chat.first_name or 'Private' if chat else 'N/A'}</code>\n"
            f"🆔 Chat ID: <code>{chat.id if chat else 'N/A'}</code>"
        )

        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(info_text, reply_markup=reply_markup)

    async def _handle_random(self, query: CallbackQuery) -> None:
        """Handles the 'random' callback by showing a random number.

        Args:
            query: The `CallbackQuery` object from the event.
        """
        import random

        random_num = random.randint(1, 100)
        random_emoji = random.choice(["🎲", "🎯", "🎰", "🎪", "🎨", "🎭", "🎸", "🎺"])

        random_text = (
            f"🎲 <b>Random Result</b>\n\n"
            f"{random_emoji} Number: <code>{random_num}</code>\n"
            f"🎯 Range: 1-100"
        )

        keyboard = [
            [InlineKeyboardButton("🎲 Again", callback_data="random")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(random_text, reply_markup=reply_markup)

    async def _handle_time(self, query: CallbackQuery) -> None:
        """Handles the 'time' callback by showing the current date and time.

        Args:
            query: The `CallbackQuery` object from the event.
        """
        from datetime import datetime, timedelta

        utc_now = datetime.utcnow() + timedelta(hours=7)

        time_text = (
            f"⏰ <b>Current Time</b>\n\n"
            f"🌍 GMT+7: <code>{utc_now.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            f"📅 Day: <code>{utc_now.strftime('%A')}</code>\n"
            f"📆 Date: <code>{utc_now.strftime('%B %d, %Y')}</code>"
        )

        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="time")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(time_text, reply_markup=reply_markup)

    async def _handle_refresh(self, query: CallbackQuery) -> None:
        """Handles the 'refresh' callback by regenerating the main menu.

        Args:
            query: The `CallbackQuery` object from the event.
        """
        keyboard = [
            [
                InlineKeyboardButton("📊 Status", callback_data="status"),
                InlineKeyboardButton("ℹ️ Info", callback_data="info"),
            ],
            [
                InlineKeyboardButton("🎲 Random", callback_data="random"),
                InlineKeyboardButton("⏰ Time", callback_data="time"),
            ],
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
                InlineKeyboardButton("❌ Close", callback_data="close"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        menu_text = (
            "🎛️ <b>Interactive Menu</b>\n\n"
            "Choose an option below:\n"
            "🔄 <i>Refreshed</i>"
        )

        await query.edit_message_text(menu_text, reply_markup=reply_markup)

    async def _handle_close(self, query: CallbackQuery) -> None:
        """Handles the 'close' callback by deleting the message.

        Args:
            query: The `CallbackQuery` object from the event.
        """
        if query.message:
            await query.message.delete()

    async def _handle_counter(self, query: CallbackQuery, data: str) -> None:
        """Handles callbacks for the counter (increment, decrement, reset).

        It parses the action and current value from the callback data string to
        determine the new value and update the message.

        Args:
            query: The `CallbackQuery` object from the event.
            data: The callback data string (e.g., 'counter_inc_5').
        """
        parts = data.split("_")
        action = parts[1]  # inc, dec, or reset
        current_value = int(parts[2])

        if action == "inc":
            new_value = current_value + 1
        elif action == "dec":
            new_value = current_value - 1
        elif action == "reset":
            # The original value is passed in 'reset' to maintain context if needed
            new_value = 0
        else:
            new_value = current_value

        keyboard = [
            [
                InlineKeyboardButton("➖", callback_data=f"counter_dec_{new_value}"),
                InlineKeyboardButton("🔄", callback_data=f"counter_reset_{new_value}"),
                InlineKeyboardButton("➕", callback_data=f"counter_inc_{new_value}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        counter_text = (
            f"🔢 <b>Counter</b>\n\n" f"Current value: <code>{new_value}</code>"
        )

        await query.edit_message_text(counter_text, reply_markup=reply_markup)

    async def _handle_back_to_menu(self, query: CallbackQuery) -> None:
        """Edits the message to display the main menu again.

        Args:
            query: The `CallbackQuery` object from the event.
        """
        keyboard = [
            [
                InlineKeyboardButton("📊 Status", callback_data="status"),
                InlineKeyboardButton("ℹ️ Info", callback_data="info"),
            ],
            [
                InlineKeyboardButton("🎲 Random", callback_data="random"),
                InlineKeyboardButton("⏰ Time", callback_data="time"),
            ],
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
                InlineKeyboardButton("❌ Close", callback_data="close"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        menu_text = "🎛️ <b>Interactive Menu</b>\n\n" "Choose an option below:"

        await query.edit_message_text(menu_text, reply_markup=reply_markup)

    @listener.on_callback_query()
    async def handle_back_callback(self, ctx: listener.Context) -> None:
        """Specifically handles the 'back_to_menu' callback query.

        This listener filters only for the 'back_to_menu' data and calls the
        appropriate helper to return the user to the main menu.

        Args:
            ctx: The context containing the callback query.
        """
        query = ctx.update.callback_query
        if not query or query.data != "back_to_menu":
            return

        await query.answer()
        await self._handle_back_to_menu(query)
