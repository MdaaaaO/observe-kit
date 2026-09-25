"""Where events go, and who is told when a call raises something unexpected.

Both are Protocols: anything with the right method satisfies them, without importing this
package.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .events import ObservedEvent


@runtime_checkable
class EventSink(Protocol):
    """Receives every event: a metrics client, a database table, a queue, a list in a test."""

    def emit(self, event: ObservedEvent) -> None: ...


@runtime_checkable
class Notifier(Protocol):
    """Told about RAISED outcomes only: chat, e-mail, a pager.

    `observed` calls `error(title=..., text=...)` by keyword. A notifier with a richer
    signature (extra keyword-only arguments with defaults) still satisfies this.
    """

    def error(self, title: str, text: str) -> None: ...


class NullSink:
    """Drops every event. What a call gets when its instance has no `.sink`."""

    def emit(self, event: ObservedEvent) -> None:
        return None


class NullNotifier:
    """Tells nobody."""

    def error(self, title: str, text: str) -> None:
        return None


class MemorySink:
    """Keeps every event in a list. For tests, and for inspecting a run afterwards."""

    def __init__(self) -> None:
        self.events: list[ObservedEvent] = []

    def emit(self, event: ObservedEvent) -> None:
        self.events.append(event)

    def named(self, name: str) -> list[ObservedEvent]:
        """The events of one decorated call, oldest first."""
        return [e for e in self.events if e.name == name]
