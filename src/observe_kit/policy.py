"""What a RAISED notification may carry.

A notification leaves the process: it lands on a phone, in a chat channel, in somebody's inbox.
The log line and the event keep the whole context and the whole error; the notification's job
is "something is wrong, come and look", and it carries only what the policy allows.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .text import withhold_urls


@dataclass(frozen=True, slots=True)
class NotifyPolicy:
    """Which context fields travel, and how the error is cut down.

    Args:
        fields: Context names allowed into the message. An **allow**-list: `fields=` is chosen
            per call site, so a deny-list would have to grow with every new argument, and
            forgetting one would leak it. The default allows none.
        withheld_hint: Where to find what was withheld, e.g. "see logs/app.jsonl". Appended to
            the count of withheld fields.

    The error is always cut to its first line, with URLs withheld (`withhold_urls`), and the
    message says how many lines and fields it left out, so a policy that is too narrow shows up
    as a number instead of as a call that seemed to have no context.
    """

    fields: frozenset[str] = frozenset()
    withheld_hint: str = "see the log"

    def context(self, context: Mapping[str, object]) -> str:
        """The allowed `key=value` pairs, plus a count of the rest."""
        kept = " ".join(f"{k}={v}" for k, v in context.items() if k in self.fields)
        withheld = sum(1 for key in context if key not in self.fields)
        if not withheld:
            return kept
        note = f"({withheld} field(s) withheld — {self.withheld_hint})"
        return f"{kept} {note}" if kept else note

    def error(self, error: str | None) -> str:
        """The first line of the error with URLs withheld, plus a count of the dropped lines.

        Only the first line, because libraries append their own detail below it (Playwright's
        `Call log:`, a server's response body) and that is where identifiers tend to be. URLs are
        taken out of the line that is kept, because some errors put them in the first line.
        """
        if not error:
            return ""
        first, _, rest = error.partition("\n")
        line = withhold_urls(first).rstrip()
        dropped = len(rest.splitlines()) if rest else 0
        return f"{line} (+{dropped} line(s) withheld)" if dropped else line

    def text(self, qualname: str, error: str | None, context: Mapping[str, object]) -> str:
        """The notification body: where it raised, what it raised, the allowed context."""
        return f"{qualname}\n{self.error(error)}\n{self.context(context)}"


DEFAULT_POLICY = NotifyPolicy()
