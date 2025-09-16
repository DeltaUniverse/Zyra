import ast
import asyncio
import contextlib
import html
import inspect
import io
import time as _time
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
        if ctx.msg.from_user.id != self.bot.owner_id:
            return

        code = (
            (ctx.msg.text or "").partition(" ")[2] if ctx.msg and ctx.msg.text else ""
        )
        if not code:
            reply: Optional[Message] = ctx.msg.reply_to_message if ctx.msg else None
            code = (reply.text or reply.caption or "") if reply else ""

        sent = await ctx.respond("<code>...</code>", parse_mode="HTML")

        if not code.strip():
            await sent.edit_text(
                "<code>No Code Provided!</code>",
                reply_markup=self._buttons(),
                parse_mode="HTML",
            )
            return

        task = asyncio.create_task(self._do_exec(sent, code, ctx))
        self._tasks[sent.id] = task

    async def _do_exec(self, sent: Message, code: str, ctx: listener.Context) -> None:
        try:
            output, took_us, paste_button = await self._run_code(
                code, {"ctx": ctx, "bot": ctx.bot}
            )
        except asyncio.CancelledError:
            output, took_us, paste_button = "CancelledError", 0, None

        took_str = time.format_duration_us(took_us)
        kb = self._buttons()
        if paste_button:
            kb.inline_keyboard[0].insert(0, paste_button)

        text = f"<code>{html.escape(output)}</code>\n\n<b>{took_str}</b>"
        with contextlib.suppress(Exception):
            await sent.edit_text(text, reply_markup=kb, parse_mode="HTML")

        self._tasks.pop(sent.id, None)

    @listener.on_callback_query()
    async def handle_callback(self, ctx: listener.Context) -> None:
        query = ctx.update.callback_query if ctx.update else None
        if not query or not query.data:
            return

        if not query.data.startswith("exec:"):
            return

        if query.from_user.id != self.bot.owner_id:
            await query.answer("Who are you?", show_alert=True)
            return

        await query.answer()
        replied = query.message.reply_to_message if query.message else None
        host_msg = query.message
        if query.data == "exec:del":
            if replied:
                with contextlib.suppress(Exception):
                    await replied.delete()

            if host_msg:
                with contextlib.suppress(Exception):
                    await host_msg.delete()

            self._tasks.pop(host_msg.id, None)
            return

        if query.data == "exec:cancel":
            task = self._tasks.pop(host_msg.id, None)
            if task and not task.done():
                task.cancel()

            return

        if query.data == "exec:run":
            if not host_msg:
                return

            await host_msg.edit_text("<code>...</code>", parse_mode="HTML")
            code = ""
            if replied:
                code = (replied.text or replied.caption).partition(" ")[2] or ""

            if not code and host_msg and host_msg.text:
                code = host_msg.reply_to_message.text.partition(" ")[2]

            if not code.strip():
                await host_msg.edit_text(
                    "<code>Message Gone!</code>",
                    reply_markup=self._buttons(),
                    parse_mode="HTML",
                )
                return

            task = asyncio.create_task(self._do_exec(host_msg, code, ctx))
            self._tasks[host_msg.id] = task

    def _buttons(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Run", callback_data="exec:run"),
                    InlineKeyboardButton("Cancel", callback_data="exec:cancel"),
                ],
                [InlineKeyboardButton("Del", callback_data="exec:del")],
            ]
        )

    async def _run_code(
        self, code: str, extra_args: Dict[str, Any]
    ) -> tuple[str, int, Optional[InlineKeyboardButton]]:
        args: Dict[str, Any] = {"io": io, "inspect": inspect, "ctxlib": contextlib}
        args.update(extra_args)
        buf = io.StringIO()
        start = _time.perf_counter()
        with contextlib.redirect_stdout(buf):
            try:
                result = await self._aexec(code, args)
                output = (
                    buf.getvalue() or ("" if result is None else str(result))
                ).strip()
            except Exception as e:
                output = f"{e.__class__.__name__}:\n  {e}"

        took_us = int((_time.perf_counter() - start) * 1_000_000)
        paste_button: Optional[InlineKeyboardButton] = None
        if len(output) > 2048:
            try:
                resp = await self.bot.http.post(
                    "https://paste.rs", data=output.encode()
                )
                resp.raise_for_status()
            except Exception as e:
                output = f"{output[:1024]}...\n\n{e.__class__.__name__}:\n  {e}"
            else:
                paste_button = InlineKeyboardButton("Output", url=resp.text)
                output = f"{output[:1024]}..."

        return output, took_us, paste_button

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
