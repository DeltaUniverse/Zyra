import asyncio
import inspect
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
        for i, existing in enumerate(bucket):
            if existing.priority > priority:
                bucket.insert(i, li)
                break
        else:
            bucket.append(li)

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

            if (
                evt is None
                and name.startswith("on_")
                and (hook := name.removeprefix("on_")) in _HOOKS
            ):
                evt, flt = hook, None

            if name.startswith("cmd_"):
                primary = name[4:]
                if primary:
                    evt = evt or "command"
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
                    setattr(fn, "_flt", flt)
                    setattr(fn, "_prio", prio)

            if evt:
                self.add_listener(fn, evt, filters=flt, priority=prio)

    def unregister_module(self, mod: Any) -> None:
        mod_name = getattr(mod, "__name__", None)
        for ev in list(self.listeners):
            new_bucket: List[Listener] = []
            for li in self.listeners[ev]:
                if hasattr(li.func, "__self__") and li.func.__self__ is mod:
                    continue

                if mod_name and getattr(li.func, "__module__", None) == mod_name:
                    continue

                new_bucket.append(li)

            if new_bucket:
                self.listeners[ev] = new_bucket
            else:
                del self.listeners[ev]

        if hasattr(self, "update_module_events"):
            try:
                self.update_module_events()
            except Exception:
                pass

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

    async def _invoke(self, func: Any, update: Any, context: Any) -> None:
        try:
            sig = inspect.signature(func)
            argc = sum(
                1
                for p in sig.parameters.values()
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            )
        except Exception:
            argc = 2

        await (func(update, context) if argc >= 2 else func())

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
            if cmds and cmd_l not in {c.lower() for c in cmds}:
                continue

            tasks.add(asyncio.create_task(self._invoke(li.func, update, context)))

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
        wait: bool = True,
    ) -> None:
        if event == "message" and await self._dispatch_command(update, context):
            return

        bucket = self.listeners.get(event, [])
        if not bucket:
            return

        tasks: Set[asyncio.Task[Any]] = set()
        for li in bucket:
            if li.event in _HOOKS or await self._passes(li.filters, update, context):
                tasks.add(asyncio.create_task(self._invoke(li.func, update, context)))

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

        tasks = [
            asyncio.create_task(self._invoke(li.func, update, context)) for li in bucket
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def dispatch_event(
        self,
        event: str,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
        *,
        wait: bool = True,
    ) -> None:
        if event in _HOOKS:
            await self.emit_hook(Hooks(event), update, context)
        else:
            await self.dispatch(event, update, context, wait=wait)
