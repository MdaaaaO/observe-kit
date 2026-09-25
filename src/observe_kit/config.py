"""Process-wide defaults: the sink, notifier and notify policy used when a call has none of its own.

Set once at start-up, next to the structlog configuration:

    observe_kit.configure(sink=CountingSink(counter), notifier=Pager(), notify_policy=POLICY)

They are read on every call, not when the function is decorated, so `configure` works however
late it runs. The instance's own `.sink` / `.notifier` and a decorator's `notify_policy=` still
win; these only fill the gaps.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from .policy import NotifyPolicy
from .sinks import EventSink, Notifier


class _Keep(enum.Enum):
    KEEP = enum.auto()


KEEP = _Keep.KEEP


@dataclass(frozen=True, slots=True)
class Defaults:
    """What `configure` set. None means "no default": NullSink, no notifier, DEFAULT_POLICY."""

    sink: EventSink | None = None
    notifier: Notifier | None = None
    notify_policy: NotifyPolicy | None = None


_current = Defaults()


def configure(
    *,
    sink: EventSink | None | _Keep = KEEP,
    notifier: Notifier | None | _Keep = KEEP,
    notify_policy: NotifyPolicy | None | _Keep = KEEP,
) -> Defaults:
    """Set the process-wide defaults and return the previous ones.

    An argument left out keeps its current value; `None` clears it. `restore(previous)` undoes
    the change.
    """
    global _current
    previous = _current
    _current = Defaults(
        sink=previous.sink if sink is KEEP else sink,
        notifier=previous.notifier if notifier is KEEP else notifier,
        notify_policy=previous.notify_policy if notify_policy is KEEP else notify_policy,
    )
    return previous


def defaults() -> Defaults:
    """The defaults in effect now."""
    return _current


def restore(previous: Defaults) -> None:
    """Put back defaults returned by an earlier `configure`, e.g. at the end of a test."""
    global _current
    _current = previous
