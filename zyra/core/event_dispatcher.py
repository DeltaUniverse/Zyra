import asyncio
import contextlib
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterable,
    MutableMapping,
    MutableSequence,
    Optional,
    Tuple,
)

from telegram import Update

from .. import module
from ..listener import (
    CallbackQueryContext,
    ChosenInlineResultContext,
    Context,
    InlineQueryContext,
    Listener,
)
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

    def _merge_filters(self, *flts: Any) -> Any:
        merged = [f for f in flts if f is not None]
        if not merged:
            return None

        if len(merged) == 1:
            return merged[0]

        return merged

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
            priority=priority, event=event_name, func=function, module=mod, filter=flt
        )
        bucket = self.listeners.setdefault(event_name, [])
        bucket.append(li)
        bucket.sort()
        self.update_module_events()

    def _bind_listener(
        self, mod: module.Module, method_name: str
    ) -> Tuple[Optional[Any], Optional[Any], int]:
        func = getattr(mod, method_name, None)
        if not callable(func):
            return None, None, 100

        prio = getattr(func, "_listener_priority", 100)
        fn_flt = getattr(func, "_listener_filters", None)
        evt_flt = getattr(mod, f"{method_name}_filter", None)
        mod_flt = getattr(mod, "module_filter", None)
        flt = self._merge_filters(fn_flt or evt_flt or mod_flt)
        return func, flt, prio

    def _iter_event_methods(
        self, mod: module.Module
    ) -> Iterable[Tuple[str, str, Callable[..., Any]]]:
        for name in dir(mod):
            if not name.startswith("on_"):
                continue

            fn = getattr(mod, name)
            if not callable(fn):
                continue

            base = name[3:].split("__", 1)[0]
            yield base, name, fn

    def register_listener(
        self: "Zyra",
        mod: module.Module,
        event: str,
        func: Callable[..., Any],
        *,
        priority: int = 100,
        filters: Optional[Any] = None,
    ) -> None:
        if event in _HOOK_VALUES and filters is not None:
            self.log.warning(
                "Built-in hook '%s' cannot use filters. Ignoring filter.", event
            )
            filters = None

        if getattr(func, "_cmd_filters", None):
            self.log.warning(
                "@command.filters is only for command handlers. Ignoring on '%s'.",
                func.__name__,
            )

        self._add_listener(mod, event, func, priority=priority, flt=filters)

    def register_listeners(self: "Zyra", mod: module.Module) -> None:
        try:
            for base_event, method_name, func in self._iter_event_methods(mod):
                _, flt, prio = self._bind_listener(mod, method_name)
                self.register_listener(
                    mod, base_event, func, priority=prio, filters=flt
                )
        except Exception:
            self.unregister_listeners(mod)
            raise

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

            if isinstance(flt, (list, tuple, set)):
                for f in flt:
                    ok = await self._passes_filter(f, subject)
                    if not ok:
                        return False

                return True

            if hasattr(flt, "__call__") and not hasattr(flt, "check_update"):
                res = flt(subject)
                if asyncio.iscoroutine(res):
                    res = await res

                if isinstance(res, (list, tuple, set)):
                    for sub in res:
                        ok = await self._passes_filter(sub, subject)
                        if not ok:
                            return False

                    return True

                return bool(res)

            if hasattr(flt, "check_update"):
                target = (
                    subject
                    if isinstance(subject, Update)
                    else getattr(subject, "update", subject)
                )
                res = flt.check_update(target)
                res = await res if asyncio.iscoroutine(res) else res
                return bool(res)

            return bool(flt)
        except Exception as exc:
            self._log_exc(exc)
            return False

    async def _dispatch_command(
        self: "Zyra", update: Update, raw_context: Optional[Any] = None
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

        invoker_token, *args = parts
        full_invoker_len = len(invoker_token)
        if "@" in invoker_token:
            base, target = invoker_token.split("@", 1)
            if self.me.username and target.lower() != self.me.username.lower():
                return False

            invoker = base
            full_invoker_len = len(base) + 1 + len(target)
        else:
            invoker = invoker_token

        ctx = Context(
            bot=self,
            chat=msg.chat,
            message=msg,
            cmd_len=len(prefix) + full_invoker_len,  # accurate even with @username
            segments=[invoker] + args,
            update=update,
            raw_context=raw_context,
            last_update_time=None,
        )

        any_called = False
        tasks: set[asyncio.Task[Any]] = set()
        for li in self.listeners.get("command", []):
            if not await self._passes_filter(li.filter, ctx):
                continue

            try:
                tasks.add(self.loop.create_task(li.func(ctx)))
                any_called = True
            except Exception as exc:
                self._log_exc(exc)

        if tasks:
            await asyncio.wait(tasks)

        if any_called:
            try:
                await self.log_stat(f"cmd:{invoker}", update, raw_context)
            except Exception as exc:
                self._log_exc(exc)

        return any_called

    async def dispatch_event(
        self: "Zyra", event_name: str, *args: Any, wait: bool = True, **kwargs: Any
    ) -> None:
        if event_name not in (
            "message",
            "callback_query",
            "inline_query",
            "chosen_inline_result",
        ):
            listeners = self.listeners.get(event_name)
            if not listeners:
                return

            tasks: set[asyncio.Task[Any]] = set()
            for li in listeners:
                subject = args[0] if args else None
                if li.filter is not None and not await self._passes_filter(
                    li.filter, subject
                ):
                    continue

                try:
                    tasks.add(self.loop.create_task(li.func(*args, **kwargs)))
                except Exception as exc:
                    self._log_exc(exc)

            if tasks and wait:
                await asyncio.wait(tasks)

            return

        upd: Optional[Update] = (
            args[0] if args and isinstance(args[0], Update) else None
        )
        raw_ctx = args[1] if len(args) > 1 else None
        if not upd:
            return

        tasks: set[asyncio.Task[Any]] = set()

        if event_name == "message":
            if await self._dispatch_command(upd, raw_ctx):
                return

            msg = upd.effective_message
            text = (msg.text or msg.caption or "") if msg else ""
            segments = text.split() if text else []
            ctx = Context(
                bot=self,
                chat=msg.chat if msg else None,
                message=msg,
                cmd_len=0,
                segments=segments,
                update=upd,
                raw_context=raw_ctx,
                last_update_time=None,
            )
            for li in self.listeners.get("message", []):
                if li.filter is not None and not await self._passes_filter(
                    li.filter, ctx
                ):
                    continue

                try:
                    tasks.add(self.loop.create_task(li.func(ctx)))
                except Exception as exc:
                    self._log_exc(exc)

        elif event_name == "callback_query" and upd.callback_query:
            ctx = CallbackQueryContext(
                bot=self,
                query=upd.callback_query,
                update=upd,
                raw_context=raw_ctx,
                last_update_time=None,
            )
            for li in self.listeners.get("callback_query", []):
                if li.filter is not None and not await self._passes_filter(
                    li.filter, ctx
                ):
                    continue

                try:
                    tasks.add(self.loop.create_task(li.func(ctx)))
                except Exception as exc:
                    self._log_exc(exc)

        elif event_name == "inline_query" and upd.inline_query:
            ctx = InlineQueryContext(
                bot=self,
                query=upd.inline_query,
                update=upd,
                raw_context=raw_ctx,
                last_update_time=None,
            )
            for li in self.listeners.get("inline_query", []):
                if li.filter is not None and not await self._passes_filter(
                    li.filter, ctx
                ):
                    continue

                try:
                    tasks.add(self.loop.create_task(li.func(ctx)))
                except Exception as exc:
                    self._log_exc(exc)

        elif event_name == "chosen_inline_result" and upd.chosen_inline_result:
            ctx = ChosenInlineResultContext(
                bot=self,
                result=upd.chosen_inline_result,
                update=upd,
                raw_context=raw_ctx,
                last_update_time=None,
            )
            for li in self.listeners.get("chosen_inline_result", []):
                if li.filter is not None and not await self._passes_filter(
                    li.filter, ctx
                ):
                    continue

                try:
                    tasks.add(self.loop.create_task(li.func(ctx)))
                except Exception as exc:
                    self._log_exc(exc)

        if tasks and wait:
            await asyncio.wait(tasks)

    async def log_stat(
        self: "Zyra",
        stat_key: str,
        update: Optional[Update] = None,
        raw_context: Optional[Any] = None,
    ) -> None:
        listeners = self.listeners.get("stat_event", [])
        if not listeners:
            return

        tasks: set[asyncio.Task[Any]] = set()
        for li in listeners:
            try:
                tasks.add(self.loop.create_task(li.func(stat_key, update, raw_context)))
            except Exception as exc:
                self._log_exc(exc)

        if tasks:
            await asyncio.wait(tasks)

    def _log_exc(self, exc: BaseException) -> None:
        tb = exc.__traceback__
        while tb and tb.tb_next:
            tb = tb.tb_next

        file_path = tb.tb_frame.f_code.co_filename if tb else "?"
        line_no = tb.tb_lineno if tb else "?"
        self.log.error(f"{exc.__class__.__name__}: {exc} at {file_path}:{line_no}")
