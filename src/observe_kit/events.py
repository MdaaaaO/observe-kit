"""What one observed call produced."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class CallOutcome(StrEnum):
    """How a call ended. Exactly one per call."""

    FINISHED = "finished"  # returned normally
    EXPECTED = "expected"  # listed in `expected`: warned, re-raised
    SWALLOWED = "swallowed"  # listed in `swallow`: debug-logged, `default` returned
    RAISED = "raised"  # any other Exception: error + traceback, notified, re-raised

    @property
    def level(self) -> str:
        """The log level this outcome is written at (FINISHED's can be lowered per call)."""
        return _LEVELS[self]


_LEVELS: dict[CallOutcome, str] = {
    CallOutcome.FINISHED: "info",
    CallOutcome.EXPECTED: "warning",
    CallOutcome.SWALLOWED: "debug",
    CallOutcome.RAISED: "error",
}


@dataclass(frozen=True, slots=True)
class ObservedEvent:
    """One call, as the sink receives it."""

    name: str  # the decorator's name, e.g. "billing.charge"
    outcome: CallOutcome
    duration_ms: int
    error: str | None = None  # "TypeName: message" when the call did not finish
    context: Mapping[str, object] = field(default_factory=dict)  # observe_context + `fields`
    # The value of the argument `observed(detail=...)` names, as a string. For a call whose
    # event a later query reads back, not for log lines: it is not part of `context`.
    detail: str | None = None

    @property
    def event(self) -> str:
        """The log event name: `<name>.<outcome>`."""
        return f"{self.name}.{self.outcome}"
