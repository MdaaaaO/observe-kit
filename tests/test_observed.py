"""The observed decorator: outcomes, timing, fields, provider discovery, sync and async."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any
from unittest.mock import MagicMock

import pytest
import structlog
from structlog.testing import capture_logs

from observe_kit import CallOutcome, EventSink, MemorySink, NullSink, Provider, observed


class RecordingNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def error(self, title: str, text: str) -> None:
        self.calls.append((title, text))


class Host:
    """An object with every attribute Provider looks for."""

    def __init__(self) -> None:
        self.log = MagicMock()
        self.log.bind.return_value = self.log
        self.sink = MemorySink()
        self.notifier = RecordingNotifier()
        self.observe_context = {"run_id": 7}

    @observed("host.ok", fields=("x",))
    def ok(self, x: int, y: int = 0) -> int:
        """Adds."""
        return x + y

    @observed("host.slow", level="debug")
    def slow(self) -> None:
        time.sleep(0.02)

    @observed("host.expected", expected=(ValueError,))
    def raises_expected(self) -> None:
        raise ValueError("nope")

    @observed("host.swallow", swallow=(KeyError,), default="dflt")
    def swallows(self) -> str:
        raise KeyError("k")

    @observed("host.boom")
    def boom(self) -> None:
        raise RuntimeError("boom")

    @observed("host.both", expected=(KeyError,), swallow=(KeyError,))
    def both(self) -> None:
        raise KeyError("k")

    @observed("host.said", detail="when", swallow=(KeyError,), default="dflt")
    def said(self, when: object, *, fail: bool = False) -> str:
        if fail:
            raise KeyError("k")
        return "ok"

    @observed("host.interrupted")
    def interrupted(self) -> None:
        raise KeyboardInterrupt

    @observed("host.aok", fields=("x",))
    async def aok(self, x: int) -> int:
        await asyncio.sleep(0.02)
        return x * 2

    @observed("host.aexpected", expected=(ValueError,))
    async def aexpected(self) -> None:
        await asyncio.sleep(0)
        raise ValueError("nope")

    @observed("host.aswallow", swallow=(KeyError,), default="dflt")
    async def aswallow(self) -> str:
        await asyncio.sleep(0)
        raise KeyError("k")

    @observed("host.aboom")
    async def aboom(self) -> None:
        await asyncio.sleep(0)
        raise RuntimeError("boom")


# --- sync outcomes --------------------------------------------------------------------------


def test_finished_returns_value_and_emits() -> None:
    h = Host()
    assert h.ok(2, y=3) == 5

    ev = h.sink.events[-1]
    assert ev.name == "host.ok"
    assert ev.event == "host.ok.finished"
    assert ev.outcome is CallOutcome.FINISHED
    assert ev.error is None
    assert ev.duration_ms >= 0
    assert ev.context == {"run_id": 7, "x": 2}
    h.log.bind.assert_called_with(run_id=7, x=2)
    h.log.info.assert_called_once()
    assert h.notifier.calls == []


def test_fields_resolve_positional_or_keyword() -> None:
    h = Host()
    h.ok(x=4)
    by_keyword = h.sink.events[-1]
    h.ok(5)
    by_position = h.sink.events[-1]
    assert by_keyword.context["x"] == 4
    assert by_position.context["x"] == 5


def test_level_debug_for_finished_and_duration_is_not_truncated() -> None:
    h = Host()
    h.slow()
    h.log.debug.assert_called_once()
    assert h.sink.events[-1].duration_ms >= 15


def test_expected_is_warned_and_reraised_without_a_notification() -> None:
    h = Host()
    with pytest.raises(ValueError, match="nope"):
        h.raises_expected()
    ev = h.sink.events[-1]
    assert ev.outcome is CallOutcome.EXPECTED
    assert ev.error == "ValueError: nope"
    h.log.warning.assert_called_once()
    assert h.notifier.calls == []


def test_swallow_returns_default_at_debug() -> None:
    h = Host()
    assert h.swallows() == "dflt"
    ev = h.sink.events[-1]
    assert ev.outcome is CallOutcome.SWALLOWED
    assert ev.error == "KeyError: 'k'"
    h.log.debug.assert_called_once()


def test_raised_is_logged_with_traceback_notified_and_reraised() -> None:
    h = Host()
    with pytest.raises(RuntimeError, match="boom") as info:
        h.boom()
    ev = h.sink.events[-1]
    assert ev.outcome is CallOutcome.RAISED
    assert ev.error == "RuntimeError: boom"
    _, kwargs = h.log.error.call_args
    assert kwargs["exc_info"] is True
    assert h.notifier.calls == [
        (
            "host.boom raised RuntimeError",
            f"{__name__}.Host.boom\nRuntimeError: boom\n(1 field(s) withheld — see the log)",
        )
    ]
    # The re-raise is bare: the traceback ends in the function that raised.
    assert info.traceback[-1].name == "boom"


def test_expected_wins_when_listed_in_both() -> None:
    h = Host()
    with pytest.raises(KeyError):
        h.both()
    assert h.sink.events[-1].outcome is CallOutcome.EXPECTED


def test_base_exceptions_pass_through_unrecorded() -> None:
    h = Host()
    with pytest.raises(KeyboardInterrupt):
        h.interrupted()
    assert h.sink.events == []
    assert h.notifier.calls == []


def test_listed_base_exceptions_are_classified() -> None:
    @observed("fn.cancel", expected=(asyncio.CancelledError,))
    def cancel() -> None:
        raise asyncio.CancelledError

    sink = MemorySink()

    class Wrap:
        def __init__(self) -> None:
            self.sink = sink

        @observed("fn.cancel", expected=(asyncio.CancelledError,))
        def go(self) -> None:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        Wrap().go()
    assert sink.events[-1].outcome is CallOutcome.EXPECTED
    with pytest.raises(asyncio.CancelledError):
        cancel()


# --- detail ---------------------------------------------------------------------------------


def test_detail_records_the_named_argument_and_stays_out_of_the_context() -> None:
    h = Host()
    assert h.said("2026-09-23T23:30:00+02:00") == "ok"
    ev = h.sink.events[-1]
    assert ev.detail == "2026-09-23T23:30:00+02:00"
    assert ev.context == {"run_id": 7}
    h.log.bind.assert_called_with(run_id=7)


def test_detail_is_none_when_not_asked_for_or_none() -> None:
    h = Host()
    h.ok(1)
    assert h.sink.events[-1].detail is None
    h.said(None)
    assert h.sink.events[-1].detail is None


def test_detail_is_kept_beside_the_error_when_the_call_did_not_finish() -> None:
    h = Host()
    h.said("reach", fail=True)
    ev = h.sink.events[-1]
    assert ev.outcome is CallOutcome.SWALLOWED
    assert ev.detail == "reach"
    assert ev.error == "KeyError: 'k'"


# --- async ----------------------------------------------------------------------------------


def test_async_finished_is_timed_across_the_await() -> None:
    h = Host()
    assert asyncio.run(h.aok(3)) == 6
    ev = h.sink.events[-1]
    assert ev.outcome is CallOutcome.FINISHED
    assert ev.context == {"run_id": 7, "x": 3}
    assert ev.duration_ms >= 15  # the await is inside the timing, not just the coroutine's creation


def test_async_expected_is_reraised() -> None:
    h = Host()
    with pytest.raises(ValueError):
        asyncio.run(h.aexpected())
    assert h.sink.events[-1].outcome is CallOutcome.EXPECTED


def test_async_swallow_returns_default() -> None:
    h = Host()
    assert asyncio.run(h.aswallow()) == "dflt"
    assert h.sink.events[-1].outcome is CallOutcome.SWALLOWED


def test_async_raised_notifies() -> None:
    h = Host()
    with pytest.raises(RuntimeError):
        asyncio.run(h.aboom())
    assert h.sink.events[-1].outcome is CallOutcome.RAISED
    assert h.notifier.calls[-1][0] == "host.aboom raised RuntimeError"


def test_async_wrapper_is_still_a_coroutine_function() -> None:
    import inspect

    assert inspect.iscoroutinefunction(Host.aok)
    assert Host.aok.__name__ == "aok"


# --- decoration ------------------------------------------------------------------------------


def test_generators_are_refused_at_decoration() -> None:
    def gen() -> Iterator[int]:
        yield 1

    async def agen() -> AsyncIterator[int]:
        yield 1

    with pytest.raises(TypeError, match="generator"):
        observed("fn.gen")(gen)
    with pytest.raises(TypeError, match="generator"):
        observed("fn.agen")(agen)


def test_wraps_preserves_metadata() -> None:
    assert Host.ok.__name__ == "ok"
    assert Host.ok.__doc__ == "Adds."


def test_malformed_call_raises_the_real_type_error() -> None:
    h = Host()
    bad: Any = h.ok
    with pytest.raises(TypeError):
        bad(1, 2, 3)
    assert h.sink.events[-1].outcome is CallOutcome.RAISED
    assert h.sink.events[-1].context == {"run_id": 7}


# --- provider -------------------------------------------------------------------------------


def test_plain_function_gets_a_structlog_logger() -> None:
    @observed("fn.double", fields=("a",))
    def double(a: int) -> int:
        return a * 2

    with capture_logs() as logs:
        assert double(3) == 6
    [line] = logs
    assert line["event"] == "fn.double.finished"
    assert line["a"] == 3
    assert line["log_level"] == "info"
    assert isinstance(line["duration_ms"], int)


def test_provider_falls_back_when_attributes_are_the_wrong_shape() -> None:
    class Odd:
        log = "not a logger"
        sink = object()
        notifier = 42
        observe_context = ["not", "a", "mapping"]

    args = (Odd(),)
    assert callable(Provider.logger(args, "x").bind)
    assert isinstance(Provider.sink(args), NullSink)
    assert Provider.notifier(args) is None
    assert Provider.context(args) == {}


def test_a_real_structlog_logger_on_the_instance_is_used() -> None:
    class WithLog:
        def __init__(self) -> None:
            self.log = structlog.get_logger("custom").bind(component="w")

        @observed("with.log")
        def go(self) -> None:
            return None

    with capture_logs() as logs:
        WithLog().go()
    assert logs[0]["component"] == "w"


def test_memory_sink_is_an_event_sink_and_filters_by_name() -> None:
    sink = MemorySink()
    assert isinstance(sink, EventSink)
    assert isinstance(NullSink(), EventSink)

    class Uses:
        def __init__(self) -> None:
            self.sink = sink

        @observed("a")
        def a(self) -> None:
            return None

        @observed("b")
        def b(self) -> None:
            return None

    u = Uses()
    u.a()
    u.b()
    u.a()
    assert [e.name for e in sink.named("a")] == ["a", "a"]
    assert CallOutcome.RAISED.level == "error"
