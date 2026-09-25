"""bind(): block-scoped context fields, merged under observe_context and fields=."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from observe_kit import MemorySink, bind, configure, observed, restore
from observe_kit.binding import bound


@pytest.fixture
def sink() -> Iterator[MemorySink]:
    sink = MemorySink()
    previous = configure(sink=sink)
    yield sink
    restore(previous)


@observed("mod.work", fields=("x",))
def work(x: int) -> int:
    return x


@observed("mod.awork")
async def awork() -> None:
    await asyncio.sleep(0)


class Host:
    def __init__(self, sink: MemorySink) -> None:
        self.sink = sink
        self.observe_context = {"run_id": "instance"}

    @observed("host.work", fields=("x",))
    def work(self, x: int) -> int:
        return x


def test_bound_fields_reach_the_event(sink: MemorySink) -> None:
    with bind(run_id=7):
        work(1)
    [event] = sink.named("mod.work")
    assert event.context == {"run_id": 7, "x": 1}


def test_nested_merge_inner_wins_and_restores(sink: MemorySink) -> None:
    with bind(run_id=7, tenant="a"):
        with bind(tenant="b"):
            assert bound() == {"run_id": 7, "tenant": "b"}
            work(1)
        assert bound() == {"run_id": 7, "tenant": "a"}
        work(2)
    assert bound() == {}
    work(3)
    assert [e.context for e in sink.named("mod.work")] == [
        {"run_id": 7, "tenant": "b", "x": 1},
        {"run_id": 7, "tenant": "a", "x": 2},
        {"x": 3},
    ]


def test_restores_on_exception() -> None:
    with pytest.raises(ValueError), bind(run_id=7):
        raise ValueError
    assert bound() == {}


def test_precedence_bind_lt_instance_lt_fields(sink: MemorySink) -> None:
    with bind(run_id="bind", x="bind", only="bind"):
        Host(sink).work(1)
    [event] = sink.named("host.work")
    assert event.context == {"run_id": "instance", "x": 1, "only": "bind"}


def test_asyncio_tasks_are_isolated(sink: MemorySink) -> None:
    async def job(n: int) -> None:
        with bind(job=n):
            await asyncio.sleep(0)
            await awork()

    async def main() -> None:
        with bind(run_id=7):
            await asyncio.gather(job(1), job(2))
        assert bound() == {}

    asyncio.run(main())
    contexts = sorted((e.context for e in sink.named("mod.awork")), key=lambda c: str(c["job"]))
    assert contexts == [{"run_id": 7, "job": 1}, {"run_id": 7, "job": 2}]


def test_new_thread_needs_copy_context(sink: MemorySink) -> None:
    import contextvars
    import threading

    with bind(run_id=7):
        plain = threading.Thread(target=work, args=(1,))
        copied = threading.Thread(target=contextvars.copy_context().run, args=(work, 2))
        plain.start(), copied.start()
        plain.join(), copied.join()
    contexts = sorted((e.context for e in sink.named("mod.work")), key=lambda c: str(c["x"]))
    assert contexts == [{"x": 1}, {"run_id": 7, "x": 2}]
