import asyncio
from typing import Any, List, Optional, Set, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from ..listener import Hooks, Listener

_HOOKS = {e.value for e in Hooks}


class EventDispatcher:
    __slots__ = ()

    listeners: dict[str, List[Listener]]
    prefixes: tuple[str, ...]
    bot_username: Optional[str]

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        self.listeners = {}
        try:
            pref = self.config["bot"]["prefix"]
            self.prefixes = (
                tuple(pref) if isinstance(pref, (list, tuple, set)) else (str(pref),)
            )
        except Exception:
            self.prefixes = ("/",)

        self.bot_username = None
        super().__init__(**kwargs)

    def add_listener(
        self, func: Any, event: str, *, filters: Any = None, priority: int = 100
    ) -> None:
        li = Listener(
            priority=priority,
            event=event,
            func=func,
            filters=filters if event not in _HOOKS else None,
        )
        bucket = self.listeners.setdefault(event, [])

        insert_pos = len(bucket)
        for i, existing in enumerate(bucket):
            if existing.priority > priority:
                insert_pos = i
                break

        bucket.insert(insert_pos, li)

        if hasattr(self, "update_module_events"):
            try:
                self.update_module_events()
            except Exception:
                pass

    def register_module(self, mod: Any) -> None:
        for name in dir(mod):
            fn = getattr(mod, name)
            if not callable(fn):
                continue

            evt = getattr(fn, "_evt", None)
            flt = getattr(fn, "_flt", None)
            prio = getattr(fn, "_prio", 100)
            cmds = getattr(fn, "_cmds", None)

            if name.startswith("cmd_"):
                primary = name[4:]
                if primary:
                    if evt is None:
                        evt = "command"

                    if evt == "command":
                        merged: List[str] = []
                        seen = set()
                        for c in (primary,) + tuple(cmds or ()):
                            k = c.lower()
                            if k not in seen:
                                seen.add(k)
                                merged.append(c)

                        cmds = tuple(merged)
                        setattr(fn, "_cmds", cmds)
                        setattr(fn, "_evt", evt)
                        if flt is None:
                            flt = None

                        setattr(fn, "_flt", flt)
                        setattr(fn, "_prio", prio)

            if evt is not None:
                self.add_listener(fn, evt, filters=flt, priority=prio)

    def unregister_module(self, mod: Any) -> None:
        mod_name = getattr(mod, "__name__", None)
        for ev in list(self.listeners):
            self.listeners[ev] = [
                li for li in self.listeners[ev] if li.func.__module__ != mod_name
            ]
            if not self.listeners[ev]:
                del self.listeners[ev]

        if hasattr(self, "update_module_events"):
            try:
                self.update_module_events()
            except Exception:
                pass

    def register_listeners(self, mod: Any) -> None:
        self.register_module(mod)

    def unregister_listeners(self, mod: Any) -> None:
        self.unregister_module(mod)

    async def _passes(
        self, flt: Any, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        if flt is None:
            return True

        if isinstance(flt, (list, tuple, set)):
            for f in flt:
                if not await self._passes(f, update, context):
                    return False

            return True

        if callable(flt) and not hasattr(flt, "check_update"):
            res = flt(update, context)
            if asyncio.iscoroutine(res):
                res = await res

            if isinstance(res, (list, tuple, set)):
                for sub in res:
                    if not await self._passes(sub, update, context):
                        return False

                return True

            return bool(res)

        if hasattr(flt, "check_update"):
            res = flt.check_update(update)
            if asyncio.iscoroutine(res):
                res = await res

            return bool(res)

        return bool(flt)

    def _extract_command(self, update: Update) -> Optional[Tuple[str, List[str]]]:
        msg = update.effective_message
        if not msg:
            return None

        text = msg.text or msg.caption
        if not text:
            return None

        for prefix in self.prefixes:
            if text.startswith(prefix):
                parts = text[len(prefix) :].split()
                if not parts:
                    return None

                token = parts[0]
                if "@" in token:
                    base, at_user = token.split("@", 1)
                    if (
                        self.bot_username
                        and at_user.lower() != self.bot_username.lower()
                    ):
                        return None

                    return base, parts[1:]

                return token, parts[1:]

        return None

    async def _dispatch_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        parsed = self._extract_command(update)
        if not parsed:
            return False

        cmd, _args = parsed
        cmd_l = cmd.lower()
        bucket = self.listeners.get("command", [])
        if not bucket:
            return False

        tasks: Set[asyncio.Task[Any]] = set()
        for li in bucket:
            if not await self._passes(li.filters, update, context):
                continue

            cmds = getattr(li.func, "_cmds", None)
            if cmds is not None:
                if cmd_l not in {c.lower() for c in cmds}:
                    continue

            tasks.add(asyncio.create_task(li.func(update, context)))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            return True

        return False

    async def dispatch(
        self,
        event: str,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        wait: bool = True
    ) -> None:
        if event == "message" and await self._dispatch_command(update, context):
            return

        bucket = self.listeners.get(event, [])
        if not bucket:
            return

        tasks: Set[asyncio.Task[Any]] = set()
        for li in bucket:
            if li.event in _HOOKS or await self._passes(li.filters, update, context):
                tasks.add(asyncio.create_task(li.func(update, context)))

        if tasks and wait:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def emit_hook(
        self,
        hook: Hooks,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
    ) -> None:
        ev = hook.value
        bucket = self.listeners.get(ev, [])
        if not bucket:
            return

        tasks = [asyncio.create_task(li.func(update, context)) for li in bucket]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def on_load(
        self,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
    ) -> None:
        await self.emit_hook(Hooks.LOAD, update, context)

    async def on_start(
        self,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
    ) -> None:
        await self.emit_hook(Hooks.START, update, context)

    async def on_started(
        self,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
    ) -> None:
        await self.emit_hook(Hooks.STARTED, update, context)

    async def on_stop(
        self,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
    ) -> None:
        await self.emit_hook(Hooks.STOP, update, context)

    async def on_stopped(
        self,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
    ) -> None:
        await self.emit_hook(Hooks.STOPPED, update, context)

    async def dispatch_event(
        self,
        event: str,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
        *,
        wait: bool = True
    ) -> None:
        if event == Hooks.LOAD.value:
            await self.on_load(update, context)
        elif event == Hooks.START.value:
            await self.on_start(update, context)
        elif event == Hooks.STARTED.value:
            await self.on_started(update, context)
        elif event == Hooks.STOP.value:
            await self.on_stop(update, context)
        elif event == Hooks.STOPPED.value:
            await self.on_stopped(update, context)
        else:
            await self.dispatch(event, update, context, wait=wait)
