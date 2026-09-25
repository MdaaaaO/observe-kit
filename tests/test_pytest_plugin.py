"""The observed_events fixture and MemorySink.assert_one."""

from __future__ import annotations

import asyncio

import pytest

from observe_kit import CallOutcome, MemorySink, ObservedEvent, defaults, observed

pytest_plugins = ["pytester"]


@observed("mod.work", fields=("x",), expected=(KeyError,))
def work(x: int) -> int:
    if x < 0:
        raise KeyError(x)
    return x


def test_fixture_is_the_configured_sink(observed_events: MemorySink) -> None:
    assert defaults().sink is observed_events
    work(1)
    event = observed_events.assert_one("mod.work")
    assert event.context == {"x": 1}


def test_fixture_is_fresh_per_test(observed_events: MemorySink) -> None:
    assert observed_events.events == []


def test_fixture_is_removed_after_the_test(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        from observe_kit import defaults

        def test_uses(observed_events):
            assert defaults().sink is observed_events

        def test_after():
            assert defaults().sink is None
        """
    )
    pytester.runpytest().assert_outcomes(passed=2)


def test_assert_one_filters_by_outcome(observed_events: MemorySink) -> None:
    work(1)
    with pytest.raises(KeyError):
        work(-1)
    assert observed_events.assert_one("mod.work", CallOutcome.EXPECTED).context == {"x": -1}
    assert observed_events.assert_one("mod.work", CallOutcome.FINISHED).context == {"x": 1}


def test_assert_one_lists_what_was_recorded() -> None:
    sink = MemorySink()
    with pytest.raises(AssertionError, match="found 0; recorded:\n  \\(none\\)"):
        sink.assert_one("mod.work")
    sink.emit(_event())
    sink.emit(_event())
    with pytest.raises(AssertionError, match=r"expected one mod.work event, found 2") as info:
        sink.assert_one("mod.work")
    assert "mod.work.finished {'x': 1}" in str(info.value)
    with pytest.raises(AssertionError, match=r"one mod.work.raised event, found 0"):
        sink.assert_one("mod.work", CallOutcome.RAISED)


def _event() -> ObservedEvent:
    return ObservedEvent(
        name="mod.work", outcome=CallOutcome.FINISHED, duration_ms=1, context={"x": 1}
    )


@observed("mod.awork")
async def awork() -> int:
    await asyncio.sleep(0)
    return 1


def test_fixture_catches_async_calls(observed_events: MemorySink) -> None:
    assert asyncio.run(awork()) == 1
    assert observed_events.assert_one("mod.awork", CallOutcome.FINISHED).duration_ms >= 0
