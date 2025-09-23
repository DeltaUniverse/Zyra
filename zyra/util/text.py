from typing import Any, Iterable, Sequence, Tuple


class Redactor:
    __slots__ = ("_tokens", "_min_len", "_replacement")

    def __init__(
        self,
        tokens: Iterable[str] = (),
        *,
        min_len: int = 6,
        replacement: str = "[REDACTED]"
    ) -> None:
        clean = {str(t) for t in tokens if t and len(str(t)) >= min_len}
        self._tokens: Tuple[str, ...] = tuple(sorted(clean, key=len, reverse=True))
        self._min_len = int(min_len)
        self._replacement = str(replacement)

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "Redactor":
        tokens: set[str] = set()
        bot_token = (config.get("telegram") or {}).get("token")
        if bot_token:
            tokens.add(str(bot_token))

        extra: Sequence[str] = (config.get("bot") or {}).get("redact", {}).get(
            "extra_strings", []
        ) or ()
        for s in extra:
            if s:
                tokens.add(str(s))

        return cls(tokens)

    def with_extra(self, tokens: Iterable[str]) -> "Redactor":
        return Redactor(
            [*self._tokens, *tokens],
            min_len=self._min_len,
            replacement=self._replacement,
        )

    def redact(self, text: str) -> str:
        if not text or not self._tokens:
            return text

        if not any((t in text for t in self._tokens)):
            return text

        out = text
        for t in self._tokens:
            if t in out:
                out = out.replace(t, self._replacement)

        return out
