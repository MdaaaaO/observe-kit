"""@observed: timing, outcome classification, structured logs and events for any call.

    from observe_kit import observed

    class Billing:
        def __init__(self, log, sink):          # Provider finds these by name
            self.log, self.sink = log, sink

        @observed("billing.charge", expected=(CardDeclined,), fields=("customer_id",))
        def charge(self, customer_id: str, cents: int) -> Receipt: ...

Every call emits `billing.charge.finished` (or `.expected`, `.swallowed`, `.raised`) with
`duration_ms` and `customer_id`, as a structlog line and as an `ObservedEvent` to the sink.
"""

from .decorator import observed
from .events import CallOutcome, ObservedEvent
from .policy import DEFAULT_POLICY, NotifyPolicy
from .provider import Provider
from .sinks import EventSink, MemorySink, Notifier, NullNotifier, NullSink
from .text import withhold_urls

__all__ = [
    "DEFAULT_POLICY",
    "CallOutcome",
    "EventSink",
    "MemorySink",
    "Notifier",
    "NotifyPolicy",
    "NullNotifier",
    "NullSink",
    "ObservedEvent",
    "Provider",
    "observed",
    "withhold_urls",
]
