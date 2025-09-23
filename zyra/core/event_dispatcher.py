import asyncio
import contextlib
from enum import Enum
from typing import TYPE_CHECKING, Any, MutableMapping, MutableSequence, Optional

from telegram import CallbackQuery, Update
from telegram.ext import CallbackContext

from .. import module
from ..listener import Context, Listener
from .base import ZyraBase

if TYPE_CHECKING:
    from .bot import Zyra


class Hooks(str, Enum):
    LOAD = "load"
    START = "start"
    STARTED = "started"
    STOP = "stop"
    STOPPED = "stopped"


_HOOK_VALUES = {e.value for e in Hooks}


class EventDispatcher(ZyraBase):
    listeners: MutableMapping[str, MutableSequence[Listener]]

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        self.listeners = {}
        super().__init__(**kwargs)

    def _add_listener(
        self: "Zyra",
        mod: module.Module,
        event_name: str,
        function: Any,
        *,
        priority: int = 100,
        flt: Optional[Any] = None,
    ) -> None:
        li = Listener(
            event=event_name, func=function, module=mod, priority=priority, flt=flt
        )
        bucket = self.listeners.setdefault(event_name, [])
        bucket.append(li)
        bucket.sort()
        self.update_module_events()

    def register_listeners(self: "Zyra", mod: module.Module) -> None:
        # Message listeners
        if hasattr(mod, "on_message") and callable(getattr(mod, "on_message")):
            self._add_listener(
                mod,
                "message",
                getattr(mod, "on_message"),
                priority=100,
                flt=getattr(mod, "on_message_filter", None),
            )
        # Command listeners
        if hasattr(mod, "on_command") and callable(getattr(mod, "on_command")):
            self._add_listener(
                mod,
                "command",
                getattr(mod, "on_command"),
                priority=100,
                flt=getattr(mod, "on_command_filter", None),
            )
        # Callback query listeners
        if hasattr(mod, "on_callback_query") and callable(
            getattr(mod, "on_callback_query")
        ):
            self._add_listener(
                mod,
                "callback_query",
                getattr(mod, "on_callback_query"),
                priority=100,
                flt=getattr(mod, "on_callback_query_filter", None),
            )
        # Hook listeners: support on_load/on_start/... dengan event bucket "load"/"start"/...
        for hk in Hooks:
            meth = f"on_{hk.value}"
            if hasattr(mod, meth) and callable((bound := getattr(mod, meth))):
                self._add_listener(mod, hk.value, bound, priority=0)

    def unregister_listeners(self: "Zyra", mod: module.Module) -> None:
        to_remove = [
            li for group in self.listeners.values() for li in group if li.module == mod
        ]
        for li in to_remove:
            bucket = self.listeners.get(li.event)
            if not bucket:
                continue

            with contextlib.suppress(ValueError):
                bucket.remove(li)

            if not bucket:
                self.listeners.pop(li.event, None)

        self.update_module_events()

    async def _passes_filter(self, flt: Any, subject: Any) -> bool:
        try:
            if flt is None:
                return True

            if hasattr(flt, "check_update"):
                res = flt.check_update(
                    subject
                    if isinstance(subject, Update)
                    else getattr(subject, "update", None) or subject
                )
                return bool(await res if asyncio.iscoroutine(res) else res)

            if callable(flt):
                res = flt(subject)
                return bool(await res if asyncio.iscoroutine(res) else res)

            self.log.warning("Unknown filter type %r; ignoring.", type(flt))
            return True
        except Exception as exc:
            self._log_exc(exc)
            return False

    async def _dispatch_command(
        self: "Zyra", update: Update, raw_context: Optional[CallbackContext] = None
    ) -> bool:
        msg = update.effective_message
        text = (msg.text or msg.caption) if msg else None
        if not text:
            return False

        prefixes = getattr(self, "prefixes", (getattr(self, "prefix", "/"),))
        prefix = next((p for p in prefixes if text.startswith(p)), None)
        if not prefix:
            return False

        parts = text[len(prefix) :].split()
        if not parts:
            return False

        invoker, *args = parts
        ctx = Context(
            bot=self,
            chat=msg.chat,
            message=msg,
            cmd_len=len(prefix) + len(invoker),
            segments=[invoker] + args,
            update=update,
            last_update_time=None,
        )
        ctx.raw_context = raw_context

        any_called = False
        for li in self.listeners.get("command", []):
            if not await self._passes_filter(li.filter, update):
                continue

            try:
                await li.func(ctx)
                any_called = True
            except Exception as exc:
                self._log_exc(exc)

        if any_called:
            try:
                await self.log_stat(f"cmd:{invoker}", update, raw_context)
            except Exception as exc:
                self._log_exc(exc)

        return any_called

    async def dispatch_event(
        self: "Zyra", event_name: str, *args: Any, **kwargs: Any
    ) -> None:

        if event_name not in ("message", "callback_query"):
            group = self.listeners.get(event_name)
            if not group:
                return

            for li in group:
                try:
                    await li.func(*args, **kwargs)
                except Exception as exc:
                    self._log_exc(exc)

            return

        if event_name == "message" and args and isinstance(args[0], Update):
            upd: Update = args[0]
            raw_ctx: Optional[CallbackContext] = (
                args[1]
                if len(args) > 1 and isinstance(args[1], CallbackContext)
                else None
            )
            if await self._dispatch_command(upd, raw_ctx):
                return

            msg = upd.effective_message
            text = msg.text or msg.caption or "" if msg else ""
            segments = text.split() if text else []
            ctx = Context(
                bot=self,
                chat=msg.chat if msg else None,
                message=msg,
                cmd_len=0,
                segments=segments,
                update=upd,
                last_update_time=None,
            )
            ctx.raw_context = raw_ctx

            any_called = False
            for li in self.listeners.get("message", []):
                if not await self._passes_filter(li.filter, upd):
                    continue

                try:
                    await li.func(ctx)
                    any_called = True
                except Exception as exc:
                    self._log_exc(exc)

            if any_called:
                await self.log_stat("msg", upd, raw_ctx)

            return

        # Callback query path
        if event_name == "callback_query" and args:
            query: Optional[CallbackQuery] = None
            first = args[0]
            if isinstance(first, Update):
                query = first.callback_query
            elif isinstance(first, CallbackQuery):
                query = first

            if not query:
                return

            for li in self.listeners.get("callback_query", []):
                if not await self._passes_filter(li.filter, query):
                    continue

                try:
                    await li.func(query)
                except Exception as exc:
                    self._log_exc(exc)

            return

    async def log_stat(
        self: "Zyra",
        stat_key: str,
        update: Optional[Update] = None,
        raw_context: Optional[CallbackContext] = None,
    ) -> None:
        for li in self.listeners.get("stat_event", []):
            try:
                await li.func(stat_key, update, raw_context)
            except Exception as exc:
                self._log_exc(exc)

    def _log_exc(self, exc: BaseException) -> None:
        tb = exc.__traceback__
        while tb and tb.tb_next:
            tb = tb.tb_next

        file_path = tb.tb_frame.f_code.co_filename if tb else "?"
        line_no = tb.tb_lineno if tb else "?"
        self.log.error(f"{exc.__class__.__name__}: {exc} at {file_path}:{line_no}")
