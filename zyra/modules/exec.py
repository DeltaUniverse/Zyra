from __future__ import annotations

import ast
import asyncio
import contextlib
import html
import inspect
import io
import os
from typing import Any, ClassVar, Dict, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message

from .. import listener, module
from ..util import time


class Exec(module.Module):
    name: ClassVar[str] = "exec"
    _tasks: Dict[int, asyncio.Task]

    async def on_load(self) -> None:
        self._tasks = {}

    @listener.on_commands("exec", "e")
    async def exec_command(self, ctx: listener.Context) -> None:
        if not ctx.msg or ctx.msg.from_user.id != self.bot.owner_id:
            return

        code = (ctx.msg.text or "").partition(" ")[2]
        if not code:
            reply: Optional[Message] = ctx.msg.reply_to_message
            code = reply.text or reply.caption or "" if reply else ""

        sent = await ctx.respond(
            "<code>...</code>",
            reply_markup=self._buttons(running=True),
            parse_mode="HTML",
            allow_sending_without_reply=True,
        )
        if not (code or "").strip():
            with contextlib.suppress(Exception):
                await sent.edit_text(
                    "<code>No Code Provided!</code>", parse_mode="HTML"
                )

            return

        task = asyncio.create_task(self._do_exec(sent, code, ctx))
        self._tasks[sent.id] = task

    async def _do_exec(self, sent: Message, code: str, ctx: listener.Context) -> None:
        start_us = time.usec()
        try:
            output = await self._run_code(
                code, {"ctx": ctx, "bot": ctx.bot, "time": time}
            )
            took_us = time.usec() - start_us
            text = f"<code>{html.escape(output)}</code>\n\n{time.format_duration_us(took_us)}"
            kb = self._buttons(running=False)
            with contextlib.suppress(Exception):
                await sent.edit_text(text, reply_markup=kb, parse_mode="HTML")
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

    @listener.on_callback_query()
    async def handle_callback(self, ctx: listener.Context) -> None:
        query = getattr(ctx.update, "callback_query", None)
        if not query or not query.data:
            return

        if not query.data.startswith("exec:"):
            return

        if query.from_user.id != self.bot.owner_id:
            await query.answer("Who are you?", show_alert=True)
            return

        await query.answer()
        host_msg = query.message
        if not host_msg:
            return

        data = query.data
        if data == "exec:del":
            replied = host_msg.reply_to_message
            if replied:
                with contextlib.suppress(Exception):
                    await replied.delete()

            with contextlib.suppress(Exception):
                await host_msg.delete()

            task = self._tasks.pop(host_msg.id, None)
            if task and (not task.done()):
                task.cancel()

            return

        if data == "exec:cancel":
            task = self._tasks.pop(host_msg.id, None)
            if task and (not task.done()):
                task.cancel()

            with contextlib.suppress(Exception):
                await host_msg.edit_text(
                    "<b>Cancelling…</b>",
                    reply_markup=self._buttons(running=False),
                    parse_mode="HTML",
                )

            return

        if data == "exec:run":
            code = ""
            replied = host_msg.reply_to_message
            if replied:
                code = replied.text or replied.caption or ""
                if code.startswith(("/exec", ".exec", "/e", ".e")):
                    code = code.partition(" ")[2]

            if not code and host_msg.text:
                rt = host_msg.reply_to_message
                if rt and (rt.text or rt.caption):
                    raw = rt.text or rt.caption
                    code = raw.partition(" ")[2] if raw else ""

            if not (code or "").strip():
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

            task = asyncio.create_task(self._do_exec(host_msg, code, ctx))
            self._tasks[host_msg.id] = task
            return

    def _buttons(self, *, running: bool) -> InlineKeyboardMarkup:
        row = [InlineKeyboardButton("Run", callback_data="exec:run")]
        if running:
            row.append(InlineKeyboardButton("Cancel", callback_data="exec:cancel"))

        return InlineKeyboardMarkup(
            [row, [InlineKeyboardButton("Del", callback_data="exec:del")]]
        )

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
        fn = ast.AsyncFunctionDef(
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
        mod = ast.Module(body=[fn], type_ignores=[])
        ast.fix_missing_locations(mod)
        ns: Dict[str, Any] = {}
        exec(compile(mod, "<exec>", "exec"), ns)
        coro = await ns[fn_name](*env.values())
        return await coro if inspect.iscoroutine(coro) else coro
