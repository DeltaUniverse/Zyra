from typing import Any, Optional

from telegram import Update
from telegram.ext import ContextTypes

from ..listener import Hooks, Listener

_HOOKS = frozenset(e.value for e in Hooks)


def _base_func(fn: Any) -> Any:
    return getattr(fn, "__func__", fn)


class EventDispatcher:
    def __init__(self: "Zyra", **kwargs: Any) -> None:
        self.listeners = {}
        pref = self.config.get("bot", {}).get("prefix", "/")
        self.prefixes = (
            tuple(pref) if isinstance(pref, (list, tuple, set)) else (str(pref),)
        )
        super().__init__(**kwargs)

    def add_listener(
        self, func: Any, event: str, *, filters: Any = None, priority: int = 100
    ) -> None:
        li = Listener(
            priority=priority,
            event=event,
            func=func,
            filters=filters if event not in _HOOKS else None,
            self=self,
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
        cls = type(mod)
        for name in dir(mod):
            fn = getattr(mod, name, None)
            if not callable(fn):
                continue

            raw = getattr(cls, name, fn)
            base = _base_func(raw)

            evt = getattr(base, "_evt", None)
            flt = getattr(base, "_flt", None)
            prio = getattr(base, "_prio", 100)
            getattr(base, "_cmds", None)

            if name.startswith("on_"):
                hook = name[3:]
                if hook in _HOOKS:
                    self.add_listener(fn, hook, filters=None, priority=prio)
                    continue

            if evt and evt not in _HOOKS:
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

    def _extract_command(self, update: Update) -> Optional[tuple[str, list[str]]]:
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
        except Exception as e:
            self.log.exception(f"Error in listener {func.__name__}: {e}")

    async def _dispatch_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        parsed = self._extract_command(update)
        if not parsed:
            return False

        cmd, args_list = parsed
        setattr(context, "args", args_list)
        setattr(context, "command", cmd)

        bucket = self.listeners.get("command", [])
        if not bucket:
            return False

        cmd_lower = cmd.lower()
        handled = False

        for li in bucket:
            if not await li.check(update, context):
                continue

            cmds = getattr(_base_func(li.func), "_cmds", None)
            if cmds:
                cmds_lower = {c.lower() for c in cmds}
                if cmd_lower not in cmds_lower:
                    continue

            await self._invoke(li.func, update, context)
            handled = True

        return handled

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

        for li in bucket:
            if li.event in _HOOKS or await li.check(update, context):
                await self._invoke(li.func, update, context)

    async def emit_hook(
        self,
        hook: Hooks,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
    ) -> None:
        bucket = self.listeners.get(hook.value, [])
        if not bucket:
            return

        for li in bucket:
            await self._invoke(li.func, update, context)

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
