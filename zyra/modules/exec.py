import ast
import asyncio
import contextlib
import html
import inspect
import io
import os
from typing import Any, ClassVar, Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message

from .. import module
from ..listener import (
    CallbackQueryContext,
    Context,
    command,
    cq_data_prefix,
    desc,
    filters,
)
from ..util import time


def _owner_only(subject: Any) -> bool:
    bot_owner = getattr(getattr(subject, "bot", None), "owner_id", None)
    uid_msg = getattr(
        getattr(getattr(subject, "message", None), "from_user", None), "id", None
    )
    uid_cb = getattr(
        getattr(getattr(subject, "query", None), "from_user", None), "id", None
    )
    return (uid_msg or uid_cb) == bot_owner


class Exec(module.Module):
    name: ClassVar[str] = "exec"
    _tasks: Dict[int, asyncio.Task]

    async def on_load(self) -> None:
        self._tasks = {}
        self.log.info("Working")

    @desc("Execute Python code (owner only)")
    @command("exec", "e")
    @filters(_owner_only)
    async def on_command(self, ctx: Context) -> None:
        if not ctx.message:
            return

        tail = ctx.text[ctx.cmd_len :].strip() if ctx.text else ""
        code = tail or ""
        if not code and ctx.message.reply_to_message:
            code = (
                ctx.message.reply_to_message.text
                or ctx.message.reply_to_message.caption
                or ""
            ).strip()

        sent = await ctx.message.reply_text(
            "<code>...</code>",
            reply_markup=self._buttons(running=True),
            parse_mode="HTML",
            allow_sending_without_reply=True,
        )
        if not code:
            with contextlib.suppress(Exception):
                await sent.edit_text(
                    "<code>No Code Provided!</code>", parse_mode="HTML"
                )

            return

        task = asyncio.create_task(self._do_exec(sent, code, {"ctx": ctx}))
        self._tasks[sent.id] = task

    @desc("Exec control buttons (owner only)")
    @cq_data_prefix("exec:")
    @filters(_owner_only)
    async def on_callback_query(self, ctx: CallbackQueryContext) -> None:
        data = getattr(ctx.query, "data", None)
        if not data:
            return

        await ctx.answer()
        host_msg = ctx.query.message
        if not host_msg:
            return

        if data == "exec:del":
            replied = host_msg.reply_to_message
            if replied:
                with contextlib.suppress(Exception):
                    await replied.delete()

            with contextlib.suppress(Exception):
                await host_msg.delete()

            task = self._tasks.pop(host_msg.id, None)
            if task and not task.done():
                task.cancel()

            return

        if data == "exec:cancel":
            task = self._tasks.pop(host_msg.id, None)
            if task and not task.done():
                task.cancel()

            with contextlib.suppress(Exception):
                await ctx.query.edit_message_text(
                    "<b>Cancelling…</b>",
                    reply_markup=self._buttons(running=False),
                    parse_mode="HTML",
                )

            return

        if data == "exec:run":
            raw = ""
            if host_msg.reply_to_message:
                raw = (
                    host_msg.reply_to_message.text
                    or host_msg.reply_to_message.caption
                    or ""
                )

            if raw.startswith(("/exec", ".exec", "/e", ".e")):
                code = raw.partition(" ")[2]
            else:
                code = raw

            code = (code or "").strip()
            if not code:
                with contextlib.suppress(Exception):
                    await ctx.query.edit_message_text(
                        "<code>Message Gone!</code>",
                        reply_markup=self._buttons(running=False),
                        parse_mode="HTML",
                    )

                return

            with contextlib.suppress(Exception):
                await ctx.query.edit_message_text(
                    "<code>...</code>",
                    reply_markup=self._buttons(running=True),
                    parse_mode="HTML",
                )

            task = asyncio.create_task(self._do_exec(host_msg, code, {"ctx": ctx}))
            self._tasks[host_msg.id] = task

    def _buttons(self, *, running: bool) -> InlineKeyboardMarkup:
        row = [InlineKeyboardButton("Run", callback_data="exec:run")]
        if running:
            row.append(InlineKeyboardButton("Cancel", callback_data="exec:cancel"))

        return InlineKeyboardMarkup(
            [row, [InlineKeyboardButton("Del", callback_data="exec:del")]]
        )

    async def _do_exec(
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
            self._tasks.pop(getattr(sent, "id", None), None)

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
        if len(output) > limit:
            output = output[:limit] + "…"

        return output

    async def _aexec(self, code: str, env: Dict[str, Any]):
        node = ast.parse(code, mode="exec")
        if node.body and isinstance(node.body[-1], ast.Expr):
            node.body[-1] = ast.Return(value=node.body[-1].value)

        fn_name = "_zyra_aexec"

        def _mk_asyncdef():
            try:
                return ast.AsyncFunctionDef(
                    name=fn_name,
                    args=ast.arguments(
                        posonlyargs=[],
                        args=[ast.arg(arg=k) for k in env.keys()],
                        vararg=None,
                        kwonlyargs=[],
                        kw_defaults=[],
                        kwarg=None,
                        defaults=[],
                    ),
                    body=node.body,
                    decorator_list=[],
                    returns=None,
                    type_params=[],
                )
            except TypeError:
                return ast.AsyncFunctionDef(
                    name=fn_name,
                    args=ast.arguments(
                        posonlyargs=[],
                        args=[ast.arg(arg=k) for k in env.keys()],
                        vararg=None,
                        kwonlyargs=[],
                        kw_defaults=[],
                        kwarg=None,
                        defaults=[],
                    ),
                    body=node.body,
                    decorator_list=[],
                    returns=None,
                )

        fn = _mk_asyncdef()
        mod = ast.Module(body=[fn], type_ignores=[])
        ast.fix_missing_locations(mod)
        ns: Dict[str, Any] = {}
        exec(compile(mod, "<exec>", "exec"), ns)
        coro = ns[fn_name](*env.values())
        return await coro if inspect.iscoroutine(coro) else coro
