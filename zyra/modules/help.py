from __future__ import annotations

import contextlib
from typing import Any, ClassVar, Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .. import module
from ..listener import CallbackQueryContext, Context, command, cq_data_prefix, desc


class Help(module.Module):
    name: ClassVar[str] = "help"

    @desc("Show help menu")
    @command("help", "h")
    async def on_command(self, ctx: Context) -> None:
        query = " ".join(ctx.args).strip() if ctx.args else ""
        if query:
            key = self._resolve_module_key(query)
            if key:
                kb, text = self._render_module_detail(key)
                await ctx.reply(text, reply_markup=kb, parse_mode="HTML")
                return

        kb, text = self._render_home()
        await ctx.reply(text, reply_markup=kb, parse_mode="HTML")

    @desc("Help navigation")
    @cq_data_prefix("help:")
    async def on_callback_query(self, ctx: CallbackQueryContext) -> None:
        data = ctx.query.data or ""
        await ctx.answer()
        if data == "help:home":
            kb, text = self._render_home()
            with contextlib.suppress(Exception):
                await ctx.query.edit_message_text(
                    text, reply_markup=kb, parse_mode="HTML"
                )

            return

        if data.startswith("help:mod:"):
            key = data.partition("help:mod:")[2]
            kb, text = self._render_module_detail(key)
            with contextlib.suppress(Exception):
                await ctx.query.edit_message_text(
                    text, reply_markup=kb, parse_mode="HTML"
                )

            return

        if data == "help:close":
            with contextlib.suppress(Exception):
                await ctx.query.delete_message()

            return

    def _render_home(self) -> Tuple[InlineKeyboardMarkup, str]:
        mods = self._collect_from_listeners()
        rows: List[List[InlineKeyboardButton]] = []
        row: List[InlineKeyboardButton] = []
        for key, meta in mods.items():
            if not meta["cmds"]:
                continue

            label = f"{meta['title']} ({len(meta['cmds'])})"
            row.append(InlineKeyboardButton(label, callback_data=f"help:mod:{key}"))
            if len(row) == 2:
                rows.append(row)
                row = []

        if row:
            rows.append(row)

        if rows:
            rows.append([InlineKeyboardButton("✘", callback_data="help:close")])

        text = "<b>Help</b>\nSelect a module."
        kb = InlineKeyboardMarkup(
            rows if rows else [[InlineKeyboardButton("✘", callback_data="help:close")]]
        )
        return kb, text

    def _render_module_detail(self, key: str) -> Tuple[InlineKeyboardMarkup, str]:
        mods = self._collect_from_listeners()
        meta = mods.get(key)
        if not meta or not meta["cmds"]:
            kb = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("«", callback_data="help:home")],
                    [InlineKeyboardButton("✘", callback_data="help:close")],
                ]
            )
            return kb, "<b>Help</b>\nModule not found."

        lines: List[str] = [f"<b>{meta['title']}</b>"]
        for aliases, d in meta["cmds"]:
            lines.append(f"• <code>/{aliases}</code>{' — ' + d if d else ''}")

        if meta["iqs"]:
            lines.append("")
            lines.append("<b>Inline Query</b>")
            for d in meta["iqs"]:
                lines.append(f"• {d}" if d else "• —")

        if meta["cqs"]:
            lines.append("")
            lines.append("<b>Callback Buttons</b>")
            for d in meta["cqs"]:
                lines.append(f"• {d}" if d else "• —")

        if meta["cirs"]:
            lines.append("")
            lines.append("<b>Chosen Inline Result</b>")
            for d in meta["cirs"]:
                lines.append(f"• {d}" if d else "• —")

        text = "\n".join(lines)
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("«", callback_data="help:home")],
                [InlineKeyboardButton("✘", callback_data="help:close")],
            ]
        )
        return kb, text

    def _collect_from_listeners(self) -> Dict[str, Dict[str, Any]]:
        listeners = getattr(self.bot, "listeners", {}) or {}
        cmd_listeners = listeners.get("command", []) or []
        cq_listeners = listeners.get("callback_query", []) or []
        iq_listeners = listeners.get("inline_query", []) or []
        cir_listeners = listeners.get("chosen_inline_result", []) or []
        out: Dict[str, Dict[str, Any]] = {}

        def _ensure(mod_obj: Any) -> Dict[str, Any]:
            title = str(getattr(mod_obj, "name", mod_obj.__class__.__name__))
            key = self._module_key(title)
            return out.setdefault(
                key,
                {
                    "title": title,
                    "cmds": [],
                    "iqs": [],
                    "cqs": [],
                    "cirs": [],
                    "helpable": True,
                },
            )

        for li in cmd_listeners:
            mod = getattr(li, "module", None)
            fn = getattr(li, "func", None)
            if not mod or not fn:
                continue

            if not bool(getattr(mod, "helpable", True)):
                continue

            entry = _ensure(mod)
            aliases = self._aliases_for(fn)
            if not aliases:
                implied = self._implied_alias(fn)
                if implied:
                    aliases = [implied]

            if not aliases:
                continue

            dsc = self._desc_for(fn)
            entry["cmds"].append((" | ".join(sorted(set(aliases))), dsc))

        for li in iq_listeners:
            mod = getattr(li, "module", None)
            fn = getattr(li, "func", None)
            if not mod or not fn:
                continue

            if not bool(getattr(mod, "helpable", True)):
                continue

            entry = _ensure(mod)
            entry["iqs"].append(self._desc_for(fn))

        for li in cq_listeners:
            mod = getattr(li, "module", None)
            fn = getattr(li, "func", None)
            if not mod or not fn:
                continue

            if not bool(getattr(mod, "helpable", True)):
                continue

            entry = _ensure(mod)
            entry["cqs"].append(self._desc_for(fn))

        for li in cir_listeners:
            mod = getattr(li, "module", None)
            fn = getattr(li, "func", None)
            if not mod or not fn:
                continue

            if not bool(getattr(mod, "helpable", True)):
                continue

            entry = _ensure(mod)
            entry["cirs"].append(self._desc_for(fn))

        for k in list(out.keys()):
            if not out[k]["cmds"]:
                out.pop(k)

        for meta in out.values():
            meta["cmds"].sort(key=lambda x: x[0])

        return dict(sorted(out.items(), key=lambda kv: kv[1]["title"].lower()))

    def _aliases_for(self, fn: Any) -> List[str]:
        vals = getattr(fn, "_listener_aliases", None)
        if not vals:
            return []

        return [str(v).lstrip("/").split("@", 1)[0] for v in vals if v]

    def _desc_for(self, fn: Any) -> str:
        return str(getattr(fn, "_listener_desc", "") or "").strip()

    def _implied_alias(self, fn: Any) -> Optional[str]:
        name = getattr(fn, "__name__", "")
        if name.startswith("on_command__"):
            return name.split("__", 1)[1]

        return None

    def _module_key(self, title: str) -> str:
        return title.strip().lower().replace(" ", "_")

    def _resolve_module_key(self, query: str) -> Optional[str]:
        q = query.strip().lower().replace(" ", "_")
        mods = self._collect_from_listeners()
        if q in mods:
            return q

        for key, meta in mods.items():
            if meta["title"].lower() == query.strip().lower():
                return key

        for key in mods:
            if key.startswith(q):
                return key

        return None
