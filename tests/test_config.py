"""configure(): process-wide sink, notifier and notify policy."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from observe_kit import (
    DEFAULT_POLICY,
    CallOutcome,
    Defaults,
    MemorySink,
    NotifyPolicy,
    NullSink,
    Provider,
    configure,
    defaults,
    observed,
    restore,
)

LOUD = NotifyPolicy(fields=frozenset({"x"}))


class RecordingNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def error(self, title: str, text: str) -> None:
        self.calls.append((title, text))


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    previous = configure(sink=None, notifier=None, notify_policy=None)
    yield
    restore(previous)


@observed("mod.boom", fields=("x",))
def boom(x: int) -> None:
    raise RuntimeError("down")


@observed("mod.ok")
def ok() -> int:
    return 1


class Own:
    def __init__(self) -> None:
        self.sink = MemorySink()
        self.notifier = RecordingNotifier()

    @observed("own.boom")
    def boom(self) -> None:
        raise RuntimeError("down")


def test_plain_function_uses_configured_sink() -> None:
    sink = MemorySink()
    configure(sink=sink)  # after decoration: read per call
    ok()
    [event] = sink.named("mod.ok")
    assert event.outcome is CallOutcome.FINISHED


def test_configured_notifier_and_policy_apply() -> None:
    notifier = RecordingNotifier()
    configure(notifier=notifier, notify_policy=LOUD)
    with pytest.raises(RuntimeError):
        boom(3)
    [(title, text)] = notifier.calls
    assert title == "mod.boom raised RuntimeError"
    assert "x=3" in text


def test_default_policy_withholds_fields() -> None:
    notifier = RecordingNotifier()
    configure(notifier=notifier)
    with pytest.raises(RuntimeError):
        boom(3)
    [(_, text)] = notifier.calls
    assert "x=3" not in text


def test_decorator_policy_beats_configured() -> None:
    notifier = RecordingNotifier()
    configure(notifier=notifier, notify_policy=LOUD)

    @observed("mod.quiet", fields=("x",), notify_policy=DEFAULT_POLICY)
    def quiet(x: int) -> None:
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        quiet(3)
    [(_, text)] = notifier.calls
    assert "x=3" not in text


def test_instance_beats_configured() -> None:
    sink, notifier = MemorySink(), RecordingNotifier()
    configure(sink=sink, notifier=notifier)
    own = Own()
    with pytest.raises(RuntimeError):
        own.boom()
    assert sink.events == []
    assert notifier.calls == []
    assert [e.outcome for e in own.sink.events] == [CallOutcome.RAISED]
    assert len(own.notifier.calls) == 1


def test_configure_keeps_omitted_and_clears_none() -> None:
    sink, notifier = MemorySink(), RecordingNotifier()
    configure(sink=sink, notifier=notifier)
    configure(notify_policy=LOUD)
    assert defaults() == Defaults(sink=sink, notifier=notifier, notify_policy=LOUD)
    configure(sink=None)
    assert defaults() == Defaults(notifier=notifier, notify_policy=LOUD)
    assert isinstance(Provider.sink(()), NullSink)


def test_restore_undoes_configure() -> None:
    before = defaults()
    previous = configure(sink=MemorySink(), notifier=RecordingNotifier())
    assert previous == before
    restore(previous)
    assert defaults() == before
    assert Provider.notifier(()) is None
