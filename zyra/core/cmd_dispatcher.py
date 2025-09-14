import inspect
from typing import TYPE_CHECKING, Any, Iterable, MutableMapping, Optional

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import Application, ContextTypes, PrefixHandler, filters

from .. import command, module, util
from .base import ZyraBase

if TYPE_CHECKING:
    from .bot import Zyra


class CommandDispatcher(ZyraBase):
    commands: MutableMapping[str, command.Command]

    def __init__(self: "Zyra", **kwargs: Any) -> None:
        self.commands = {}
        super().__init__(**kwargs)

    def register_command(
        self: "Zyra",
        mod: module.Module,
        name: str,
        func: command.CommandFunc,
        filters_: Optional[filters.BaseFilter] = None,
        desc: Optional[str] = None,
        usage: Optional[str] = None,
        usage_optional: bool = False,
        aliases: Iterable[str] = (),
    ) -> None:
        if getattr(func, "_listener_filters", None):
            self.log.warning(
                "@listener.filters decorator only for ListenerFunc. Filters will be ignored..."
            )

        if filters_:
            self.log.debug(
                "Registering filter '%s' into '%s'", type(filters_).__name__, name
            )

        cmd = command.Command(
            name, mod, func, filters_, desc, usage, usage_optional, aliases
        )

        if name in self.commands:
            orig = self.commands[name]
            raise module.ExistingCommandError(orig, cmd)

        self.commands[name] = cmd

        for alias in cmd.aliases:
            if alias in self.commands:
                orig = self.commands[alias]
                raise module.ExistingCommandError(orig, cmd, alias=True)
            self.commands[alias] = cmd

    def unregister_command(self: "Zyra", cmd: command.Command) -> None:
        del self.commands[cmd.name]
        for alias in cmd.aliases:
            try:
                del self.commands[alias]
            except KeyError:
                continue

    def register_commands(self: "Zyra", mod: module.Module) -> None:
        for name, func in util.misc.find_prefixed_funcs(mod, "cmd_"):
            done = False
            try:
                self.register_command(
                    mod,
                    name,
                    func,
                    filters_=getattr(func, "_cmd_filters", None),
                    desc=getattr(func, "_cmd_description", None),
                    usage=getattr(func, "_cmd_usage", None),
                    usage_optional=getattr(func, "_cmd_usage_optional", False),
                    aliases=getattr(func, "_cmd_aliases", ()),
                )
                done = True
            finally:
                if not done:
                    self.unregister_commands(mod)

    def unregister_commands(self: "Zyra", mod: module.Module) -> None:
        to_unreg = []
        for name, cmd in self.commands.items():
            if name != cmd.name:
                continue
            if cmd.module == mod:
                to_unreg.append(cmd)
        for cmd in to_unreg:
            self.unregister_command(cmd)

    # kept for compatibility (not used when PrefixHandler is active)
    def command_predicate(self: "Zyra") -> filters.BaseFilter:
        class CustomCommandFilter(filters.MessageFilter):
            def __init__(self, zyra_instance: "Zyra"):
                self.zyra = zyra_instance
                super().__init__()

            async def filter(self, message) -> bool:
                if getattr(message, "via_bot", None):
                    return False

                if message.text is not None and message.text.startswith(
                    self.zyra.prefix
                ):
                    parts = message.text.split()
                    parts[0] = parts[0][len(self.zyra.prefix) :]

                    try:
                        cmd = self.zyra.commands[parts[0]]
                    except KeyError:
                        return False

                    if cmd.filters:
                        # let PTB handle combined BaseFilter normally; this branch is legacy
                        if isinstance(cmd.filters, filters.MessageFilter):
                            if inspect.iscoroutinefunction(cmd.filters.filter):
                                if not await cmd.filters.filter(message):
                                    return False
                            else:
                                if not await util.run_sync(cmd.filters.filter, message):
                                    return False
                    return True

                return False

        return CustomCommandFilter(self)

    async def on_command(
        self: "Zyra", update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        message = update.effective_message
        if not message or not message.text:
            return

        text = message.text
        if not text.startswith(self.prefix):
            return

        parts = text.split()
        if not parts:
            return

        cmd_name = parts[0][len(self.prefix) :]
        cmd = self.commands.get(cmd_name)
        if not cmd:
            return

        # PTB PrefixHandler prepares args (CallbackContext.args)
        args = list(getattr(context, "args", []) or [])
        segments = [cmd_name, *args]

        ctx = command.Context(
            self,
            message,
            len(self.prefix) + len(cmd_name) + 1,
            segments=segments,
            ptb_context=context,
        )

        try:
            ret = await cmd.func(ctx)
            if ret is not None:
                await ctx.respond(ret)
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                cmd.module.log.error(
                    f"Command '{cmd.name}' triggered a message edit with no changes"
                )
            else:
                raise

        await self.dispatch_event("command", cmd, message)

    def setup_command_handler(self: "Zyra", application: Application) -> None:
        """Setup per-command PrefixHandler (prefix is static)."""
        seen = set()
        for name, cmd in self.commands.items():
            if name != cmd.name or cmd.name in seen:
                continue
            seen.add(cmd.name)

            handler = PrefixHandler(
                prefix=self.prefix,
                command=[cmd.name, *cmd.aliases],
                callback=self.on_command,
                filters=cmd.filters,  # BaseFilter
            )
            application.add_handler(handler, group=10)
