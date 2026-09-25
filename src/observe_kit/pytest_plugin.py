"""pytest plugin, registered through the `pytest11` entry point when observe-kit is installed.

def test_declined_card_is_expected(observed_events):
    with pytest.raises(CardDeclined):
        charge("c_42", 500)
    observed_events.assert_one("billing.charge", CallOutcome.EXPECTED)
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from .config import configure, restore
from .sinks import MemorySink


@pytest.fixture
def observed_events() -> Iterator[MemorySink]:
    """A fresh MemorySink installed as the configured sink for one test, then removed.

    Calls on an instance with its own `.sink` still go there, not here.
    """
    sink = MemorySink()
    previous = configure(sink=sink)
    try:
        yield sink
    finally:
        restore(previous)
