import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Sequence

from telegram import Update
from telegram.ext import ContextTypes

from .events import Events, Hooks

Func = Callable[..., Awaitable[Any]]
Filter = Callable[..., bool | Awaitable[bool]]


@dataclass(order=True, slots=True)
class Listener:
    priority: int
    event: str = field(compare=False)
    func: Func = field(compare=False)
    filters: Optional[Filter] = field(default=None, compare=False)
    commands: Optional[Sequence[str]] = field(default=None, compare=False)
    bot: Any = field(default=None, compare=False)

    async def check(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        if self.filters is None:
            return True

        result = self.filters(update, context, self.bot)
        if inspect.isawaitable(result):
            result = await result

        return bool(result)


def unwrap_method(fn: Any) -> Any:
    return getattr(fn, "__func__", fn)


class EventBus:
    def __init__(self, bot: Any, prefixes: tuple[str, ...] = ("/")):
        self.bot = bot
        self.prefixes = prefixes
        self.listeners: dict[str, list[Listener]] = {}

    def add_listener(
        self,
        func: Func,
        event: str | Events,
        *,
        filters: Optional[Filter] = None,
        priority: int = 100,
    ) -> None:
        event_str = event.value if isinstance(event, Events) else str(event)

        listener = Listener(
            priority=priority,
            event=event_str,
            func=func,
            filters=filters if event_str not in {h.value for h in Hooks} else None,
            bot=self.bot,
        )

        bucket = self.listeners.setdefault(event_str, [])
        insert_idx = next(
            (i for i, existing in enumerate(bucket) if existing.priority > priority),
            len(bucket),
        )
        bucket.insert(insert_idx, listener)

    def remove_listeners_for_module(self, module: Any) -> None:
        module_name = getattr(module, "__name__", None)
        for event, listeners in list(self.listeners.items()):
            self.listeners[event] = [
                li
                for li in listeners
                if not (hasattr(li.func, "__self__") and li.func.__self__ is module)
                and not (
                    module_name and getattr(li.func, "__module__", None) == module_name
                )
            ]
            if not self.listeners[event]:
                del self.listeners[event]

    def extract_command(self, update: Update) -> Optional[tuple[str, list[str]]]:
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
                bot_username = getattr(self.bot, "bot_username", None)
                if bot_username and at_user.lower() != bot_username.lower():
                    return None

                return base, args

            return token, args

        return None

    async def _invoke(self, func: Func, update: Any, context: Any) -> None:
        try:
            await func(update, context)
        except TypeError:
            await func()
        except Exception as e:
            self.bot.log.exception(f"Error in listener {func.__name__}: {e}")

    async def dispatch_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> bool:
        parsed = self.extract_command(update)
        if not parsed:
            return False

        cmd, args_list = parsed
        setattr(context, "args", args_list)
        setattr(context, "command", cmd)

        bucket = self.listeners.get(Events.COMMAND.value, [])
        if not bucket:
            return False

        cmd_lower = cmd.lower()
        handled = False

        for listener in bucket:
            if not await listener.check(update, context):
                continue

            cmds = getattr(unwrap_method(listener.func), "_cmds", None)
            if cmds:
                if cmd_lower not in {c.lower() for c in cmds}:
                    continue

            await self._invoke(listener.func, update, context)
            handled = True

        return handled

    async def dispatch(
        self, event: str | Events, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        event_str = event.value if isinstance(event, Events) else str(event)

        if event_str == Events.MESSAGE.value:
            if await self.dispatch_command(update, context):
                return

        bucket = self.listeners.get(event_str, [])
        for listener in bucket:
            hook_values = {h.value for h in Hooks}
            if listener.event in hook_values or await listener.check(update, context):
                await self._invoke(listener.func, update, context)

    async def emit_hook(
        self,
        hook: Hooks,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
    ) -> None:
        bucket = self.listeners.get(hook.value, [])
        for listener in bucket:
            await self._invoke(listener.func, update, context)
