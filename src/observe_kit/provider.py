"""Find the collaborators `observed` needs on the decorated method's instance, or default.

Convention over wiring: if the object the method was called on has a `.log`, `.sink`,
`.notifier` or `.observe_context` of the right shape, it is used. Otherwise a module logger, no
sink, no notifier, no context. Plain functions always get the defaults.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import structlog

from .sinks import EventSink, Notifier, NullSink


class Provider:
    @staticmethod
    def _self(args: tuple[Any, ...]) -> Any | None:
        return args[0] if args else None

    @staticmethod
    def logger(args: tuple[Any, ...], default_name: str) -> Any:
        """The instance's `.log` if it has a `bind` method, else a module structlog logger."""
        log = getattr(Provider._self(args), "log", None)
        if log is not None and callable(getattr(log, "bind", None)):
            return log
        return structlog.get_logger(default_name)

    @staticmethod
    def sink(args: tuple[Any, ...]) -> EventSink:
        """The instance's `.sink` if it has an `emit` method, else a NullSink."""
        sink = getattr(Provider._self(args), "sink", None)
        if sink is not None and callable(getattr(sink, "emit", None)):
            return sink  # type: ignore[no-any-return]
        return NullSink()

    @staticmethod
    def notifier(args: tuple[Any, ...]) -> Notifier | None:
        """The instance's `.notifier` if it has an `error` method, else None."""
        notifier = getattr(Provider._self(args), "notifier", None)
        if notifier is not None and callable(getattr(notifier, "error", None)):
            return notifier  # type: ignore[no-any-return]
        return None

    @staticmethod
    def context(args: tuple[Any, ...]) -> Mapping[str, object]:
        """Fields bound to every event from this instance, e.g. {"run_id": ...}."""
        ctx = getattr(Provider._self(args), "observe_context", None)
        return ctx if isinstance(ctx, Mapping) else {}
