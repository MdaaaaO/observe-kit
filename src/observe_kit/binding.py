"""bind(): context fields for every call inside a block, without an instance to carry them.

    with observe_kit.bind(run_id=7, tenant="acme"):
        charge("c_42", 500)          # its log line and event carry run_id and tenant

Backed by a ContextVar: it holds for the current thread, an asyncio task sees what was bound where
it was created, and a task's own binds do not leak back. A new thread or thread-pool worker starts
without it unless the work runs through `contextvars.copy_context().run(...)`. Nested blocks
merge, the inner value wins, and each block restores what it found on exit.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from types import MappingProxyType

_EMPTY: Mapping[str, object] = MappingProxyType({})
_bound: ContextVar[Mapping[str, object]] = ContextVar("observe_kit_bound", default=_EMPTY)


@contextmanager
def bind(**fields: object) -> Iterator[None]:
    """Add `fields` to the context of every observed call inside the block.

    An instance's `observe_context` and the decorator's `fields=` win over these on a clash.
    """
    token = _bound.set(MappingProxyType({**_bound.get(), **fields}))
    try:
        yield
    finally:
        _bound.reset(token)


def bound() -> Mapping[str, object]:
    """The fields bound here and now (read-only)."""
    return _bound.get()
