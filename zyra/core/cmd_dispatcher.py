import inspect
from typing import TYPE_CHECKING, Any, Iterable, MutableMapping, Optional

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, ContextTypes, filters

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

    # kept for compatibility (not used when CommandHandler is active)
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
        """
        Entry point for PTB CommandHandler.

        Notes:
        - PTB handles the leading command prefix (defaults to '/').
          If you want a custom prefix like '.', configure it via ApplicationBuilder
          Defaults(command_prefix=self.prefix) when building the Application.
        - context.args is prepared by CommandHandler.
        """
        message = update.effective_message
        if not message:
            return

        # Prefer text; if captioned commands are desired, adjust accordingly
        text = message.text or ""
        if not text:
            return

        # Extract the command token (first word), strip prefix and optional @botusername
        first = text.split(maxsplit=1)[0]
        token = first.lstrip("/").split("@", 1)[0]

        cmd = self.commands.get(token)
        if not cmd:
            return

        args = list(getattr(context, "args", []) or [])
        segments = [token, *args]

        # Compute offset to the first arg char (best-effort; OK if no args)
        # Example: "/echo hello world" -> offset points right after "/echo "
        offset = len(first) + 1 if len(text) > len(first) else len(first)

        ctx = command.Context(
            self, message, offset, segments=segments, ptb_context=context
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
        """
        Register CommandHandler per command.

        To keep supporting a custom prefix such as '.', configure it at Application
        construction time:
            ApplicationBuilder().defaults(Defaults(command_prefix=self.prefix)).build()

        This method just binds commands (names + aliases) to this dispatcher.
        """
        seen = set()
        for name, cmd in self.commands.items():
            if name != cmd.name or cmd.name in seen:
                continue
            seen.add(cmd.name)

            handler = CommandHandler(
                command=[cmd.name, *cmd.aliases],
                callback=self.on_command,
                filters=cmd.filters,  # BaseFilter remains supported
            )
            application.add_handler(handler, group=10)
