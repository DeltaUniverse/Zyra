import ast
import asyncio
import contextlib
import html
import inspect
import io
import os
import sys
from typing import Any, Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import ContextTypes

from ..core.module import Module
from ..decorators import handler, owner_only, parse_callback
from ..util import time

PYTHON_312_PLUS = sys.version_info >= (3, 12)


class Exec(Module):
    name = "exec"

    async def on_load(self) -> None:
        self._tasks: Dict[int, asyncio.Task] = {}

    @handler(["exec", "e"], filters=owner_only, priority=100)
    async def on_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        msg = update.effective_message
        if not msg:
            return

        text = (msg.text or msg.caption or "").strip()
        code = self._extract_code(msg, text)

        sent = await msg.reply_text(
            "<code>...</code>",
            reply_markup=self._buttons(running=True),
            parse_mode="HTML",
            do_quote=True,
            allow_sending_without_reply=True,
        )

        if not code:
            with contextlib.suppress(Exception):
                await sent.edit_text(
                    "<code>No Code Provided!</code>", parse_mode="HTML"
                )

            return

        task = asyncio.create_task(
            self._execute(
                sent, code, {"update": update, "context": context, "msg": msg}
            )
        )
        self._tasks[sent.id] = task

    @handler("callback_query", filters=owner_only)
    async def on_callback_query(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        cq = update.callback_query
        if not cq:
            return

        parts = parse_callback(cq.data or "", "exec")
        if not parts:
            return

        action = parts[0] if parts else None
        host_msg = cq.message
        if not host_msg:
            return

        if action == "del":
            await self._handle_delete(host_msg)
            return

        if action == "cancel":
            await self._handle_cancel(host_msg)
            return

        if action == "run":
            await self._handle_run(host_msg, update, context)
            return

    async def _handle_delete(self, host_msg: Message) -> None:
        replied = host_msg.reply_to_message
        if replied:
            with contextlib.suppress(Exception):
                await replied.delete()

        with contextlib.suppress(Exception):
            await host_msg.delete()

        task = self._tasks.pop(host_msg.id, None)
        if task and not task.done():
            task.cancel()

    async def _handle_cancel(self, host_msg: Message) -> None:
        task = self._tasks.pop(host_msg.id, None)
        if task and not task.done():
            task.cancel()

        with contextlib.suppress(Exception):
            await host_msg.edit_text(
                "<b>Cancelling…</b>",
                reply_markup=self._buttons(running=False),
                parse_mode="HTML",
            )

    async def _handle_run(
        self, host_msg: Message, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        code = ""
        if host_msg.reply_to_message:
            raw = (
                host_msg.reply_to_message.text
                or host_msg.reply_to_message.caption
                or ""
            )
            code = self._strip_command(raw).strip()

        if not code:
            with contextlib.suppress(Exception):
                await host_msg.edit_text(
                    "<code>Message Gone!</code>",
                    reply_markup=self._buttons(running=False),
                    parse_mode="HTML",
                )

            return

        with contextlib.suppress(Exception):
            await host_msg.edit_text(
                "<code>...</code>",
                reply_markup=self._buttons(running=True),
                parse_mode="HTML",
            )

        task = asyncio.create_task(
            self._execute(
                host_msg, code, {"update": update, "context": context, "msg": host_msg}
            )
        )
        self._tasks[host_msg.id] = task

    def _strip_command(self, text: str) -> str:
        if not text:
            return ""

        if text.startswith(("/", ".")):
            return text.split(maxsplit=1)[1] if " " in text else ""

        return text

    def _extract_code(self, msg: Message, text: str) -> str:
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            return parts[1]

        if msg.reply_to_message:
            return (
                msg.reply_to_message.text or msg.reply_to_message.caption or ""
            ).strip()

        return ""

    def _buttons(self, *, running: bool) -> InlineKeyboardMarkup:
        row = [InlineKeyboardButton("Run", callback_data="exec:run")]
        if running:
            row.append(InlineKeyboardButton("Cancel", callback_data="exec:cancel"))

        return InlineKeyboardMarkup(
            [row, [InlineKeyboardButton("Del", callback_data="exec:del")]]
        )

    async def _execute(
        self, sent: Message, code: str, extra_args: Dict[str, Any]
    ) -> None:
        start_us = time.usec()
        try:
            output = await self._run_code(
                code, {"bot": self.bot, "time": time, **extra_args}
            )
            took_us = time.usec() - start_us
            text = f"<code>{html.escape(output)}</code>\n\n{time.format_duration_us(took_us)}"
            with contextlib.suppress(Exception):
                await sent.edit_text(
                    text, reply_markup=self._buttons(running=False), parse_mode="HTML"
                )
        except asyncio.CancelledError:
            took_us = time.usec() - start_us
            msg = f"<b>CancelledError</b>\n{time.format_duration_us(took_us)}"
            with contextlib.suppress(Exception):
                await sent.edit_text(
                    msg, reply_markup=self._buttons(running=False), parse_mode="HTML"
                )

            raise
        finally:
            self._tasks.pop(sent.id, None)

    async def _run_code(self, code: str, extra_args: Dict[str, Any]) -> str:
        args: Dict[str, Any] = {
            "self": self,
            "io": io,
            "inspect": inspect,
            "ctxlib": contextlib,
            "time": time,
            "asyncio": asyncio,
            "html": html,
            "os": os,
            "db": self.bot.db.pool,
        }
        args.update(extra_args)
        args = dict(sorted(args.items()))

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                result = await self._aexec(code, args)
                output = (
                    buf.getvalue() or ("" if result is None else str(result))
                ).strip()
            except Exception as e:
                output = f"{e.__class__.__name__}:\n  {e}"

        limit = 3800
        return (output[:limit] + "…") if len(output) > limit else output

    async def _aexec(self, code: str, env: Dict[str, Any]):
        node = ast.parse(code, mode="exec")
        if node.body and isinstance(node.body[-1], ast.Expr):
            node.body[-1] = ast.Return(value=node.body[-1].value)

        fn_name = "_zyra_aexec"
        args_ast = ast.arguments(
            posonlyargs=[],
            args=[ast.arg(arg=k) for k in env.keys()],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        )

        if PYTHON_312_PLUS:
            fn = ast.AsyncFunctionDef(
                name=fn_name,
                args=args_ast,
                body=node.body,
                decorator_list=[],
                returns=None,
                type_params=[],
            )
        else:
            fn = ast.AsyncFunctionDef(
                name=fn_name,
                args=args_ast,
                body=node.body,
                decorator_list=[],
                returns=None,
            )

        mod = ast.Module(body=[fn], type_ignores=[])
        ast.fix_missing_locations(mod)
        ns: Dict[str, Any] = {}
        exec(compile(mod, "<exec>", "exec"), ns)
        coro = ns[fn_name](*env.values())
        return await coro if inspect.iscoroutine(coro) else coro
