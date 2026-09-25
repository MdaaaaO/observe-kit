"""What a RAISED notification may carry."""

from __future__ import annotations

import pytest

from observe_kit import NotifyPolicy, NullNotifier, observed, withhold_urls
from observe_kit.policy import DEFAULT_POLICY

# A policy with a real allow-list, the shape an application configures once.
APP = NotifyPolicy(
    fields=frozenset({"count", "duration_ms", "run_id"}),
    withheld_hint="see logs/app.jsonl",
)


class RecordingNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def error(self, title: str, text: str) -> None:
        self.calls.append((title, text))


class Host:
    def __init__(self) -> None:
        self.notifier = RecordingNotifier()
        self.observe_context = {"run_id": 7}

    @observed("host.view", fields=("username", "count"), notify_policy=APP)
    def view(self, username: str, count: int) -> None:
        raise RuntimeError("boom")

    @observed("host.plain", notify_policy=APP)
    def plain(self) -> None:
        raise RuntimeError("boom")

    @observed("host.goto", fields=("username",), notify_policy=APP)
    def goto(self, username: str) -> None:
        raise RuntimeError(
            "Page.goto: Timeout 30000ms exceeded.\nCall log:\n  - navigating to "
            f'"https://example.com/users/{username}/", waiting until "domcontentloaded"'
        )

    @observed("host.offline", fields=("username",), notify_policy=APP)
    def offline(self, username: str) -> None:
        raise RuntimeError(f"net::ERR_INTERNET_DISCONNECTED at https://example.com/u/{username}/")

    @observed("host.default", fields=("username",))
    def default(self, username: str) -> None:
        raise RuntimeError("boom")


def test_only_allowed_fields_travel_and_the_rest_is_counted() -> None:
    h = Host()
    with pytest.raises(RuntimeError):
        h.view("someone", count=3)
    title, text = h.notifier.calls[0]
    assert title == "host.view raised RuntimeError"
    assert text.splitlines() == [
        f"{__name__}.Host.view",
        "RuntimeError: boom",
        "run_id=7 count=3 (1 field(s) withheld — see logs/app.jsonl)",
    ]


def test_nothing_withheld_says_nothing_about_withholding() -> None:
    h = Host()
    with pytest.raises(RuntimeError):
        h.plain()
    assert "withheld" not in h.notifier.calls[0][1]
    assert h.notifier.calls[0][1].endswith("\nrun_id=7")


def test_only_the_first_line_of_the_error_travels() -> None:
    h = Host()
    with pytest.raises(RuntimeError):
        h.goto("someone")
    text = h.notifier.calls[0][1]
    assert "someone" not in text
    assert "example.com" not in text
    assert "Timeout 30000ms exceeded. (+2 line(s) withheld)" in text


def test_urls_are_taken_out_of_the_line_that_is_kept() -> None:
    h = Host()
    with pytest.raises(RuntimeError):
        h.offline("someone")
    text = h.notifier.calls[0][1]
    assert "someone" not in text
    assert "net::ERR_INTERNET_DISCONNECTED at <url withheld>" in text


def test_the_default_policy_withholds_every_field() -> None:
    h = Host()
    with pytest.raises(RuntimeError):
        h.default("someone")
    text = h.notifier.calls[0][1]
    assert "someone" not in text
    assert "run_id" not in text
    assert text.endswith("(2 field(s) withheld — see the log)")


def test_policy_pieces() -> None:
    assert DEFAULT_POLICY.error(None) == ""
    assert DEFAULT_POLICY.context({}) == ""
    assert APP.context({"run_id": 1}) == "run_id=1"
    withheld = withhold_urls("see HTTPS://x.y/z?a=1 and http://q")
    assert withheld == "see <url withheld> and <url withheld>"


def test_null_notifier_accepts_the_call() -> None:
    NullNotifier().error(title="t", text="x")
