import asyncio
from typing import Any, List, Optional, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from ..listener import Hooks, Listener

_HOOKS = frozenset(e.value for e in Hooks)


class EventDispatcher:

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        self.listeners = {}
        pref = self.config.get("bot", {}).get("prefix", "/")
        self.prefixes = (
            tuple(pref) if isinstance(pref, (list, tuple, set)) else (str(pref),)
        )
        self._prefix_cache = {}
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

        insert_idx = len(bucket)
        for i, existing in enumerate(bucket):
            if existing.priority > priority:
                insert_idx = i
                break

        bucket.insert(insert_idx, li)

        if hasattr(self, "update_module_events"):
            self.update_module_events()

    def register_module(self, mod: Any) -> None:
        for name in dir(mod):
            fn = getattr(mod, name, None)
            if not callable(fn):
                continue

            evt = getattr(fn, "_evt", None)
            flt = getattr(fn, "_flt", None)
            prio = getattr(fn, "_prio", 100)
            cmds = getattr(fn, "_cmds", None)

            if evt is None and name.startswith("on_"):
                hook = name[3:]
                if hook in _HOOKS:
                    evt, flt = hook, None

            if name.startswith("cmd_"):
                primary = name[4:]
                if primary:
                    evt = evt or "command"
                    seen = set()
                    merged = []
                    for c in (primary,) + (cmds or ()):
                        k = c.lower()
                        if k not in seen:
                            seen.add(k)
                            merged.append(c)

                    fn._cmds = tuple(merged)
                    fn._evt = evt
                    fn._flt = flt
                    fn._prio = prio

            if evt:
                self.add_listener(fn, evt, filters=flt, priority=prio)

    def unregister_module(self, mod: Any) -> None:
        mod_name = getattr(mod, "__name__", None)

        for ev, listeners in list(self.listeners.items()):
            self.listeners[ev] = [
                li
                for li in listeners
                if not (hasattr(li.func, "__self__") and li.func.__self__ is mod)
                and not (mod_name and getattr(li.func, "__module__", None) == mod_name)
            ]

            if not self.listeners[ev]:
                del self.listeners[ev]

        if hasattr(self, "update_module_events"):
            self.update_module_events()

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
            if not text.startswith(prefix):
                continue

            parts = text[len(prefix) :].split(None, 1)
            if not parts:
                return None

            token = parts[0]
            args = parts[1].split() if len(parts) > 1 else []

            if "@" in token:
                base, at_user = token.split("@", 1)
                if self.me.username and at_user.lower() != self.me.username.lower():
                    return None

                return base, args

            return token, args

        return None

    async def _invoke(self, func: Any, update: Any, context: Any) -> None:
        try:
            await func(update, context)
        except TypeError:
            await func()

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

        matched = []
        for li in bucket:
            if not await self._passes(li.filters, update, context):
                continue

            cmds = getattr(li.func, "_cmds", None)
            if cmds and cmd_l not in {c.lower() for c in cmds}:
                continue

            matched.append(li.func)

        if matched:
            await asyncio.gather(
                *(self._invoke(func, update, context) for func in matched),
                return_exceptions=True
            )
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

        tasks = [
            self._invoke(li.func, update, context)
            for li in bucket
            if li.event in _HOOKS or await self._passes(li.filters, update, context)
        ]

        if tasks and wait:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def emit_hook(
        self,
        hook: Hooks,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
    ) -> None:
        bucket = self.listeners.get(hook.value, [])
        if bucket:
            await asyncio.gather(
                *(self._invoke(li.func, update, context) for li in bucket),
                return_exceptions=True
            )

    async def dispatch_event(
        self,
        event: str,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
        *,
        wait: bool = True
    ) -> None:
        if event in _HOOKS:
            await self.emit_hook(Hooks(event), update, context)
        else:
            await self.dispatch(event, update, context, wait=wait)
