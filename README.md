# observe-kit

[![PyPI](https://img.shields.io/pypi/v/observe-kit)](https://pypi.org/project/observe-kit/)
[![Python](https://img.shields.io/pypi/pyversions/observe-kit)](https://pypi.org/project/observe-kit/)
[![CI](https://github.com/MdaaaaO/observe-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/MdaaaaO/observe-kit/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

One decorator, `@observed`, that times a call, decides how it ended, writes a
[structlog](https://www.structlog.org) line and emits an event to a sink you choose. It works on
plain and `async def` functions and methods. Its only dependency is structlog.

```console
pip install observe-kit
```

```python
from observe_kit import observed


class Billing:
    def __init__(self, log, sink, notifier):
        self.log, self.sink, self.notifier = log, sink, notifier

    @observed("billing.charge", expected=(CardDeclined,), fields=("customer_id",))
    def charge(self, customer_id: str, cents: int) -> Receipt: ...
```

Each call to `charge` then produces one log line and one event:

```text
billing.charge.finished   customer_id=c_42 duration_ms=183
billing.charge.expected   customer_id=c_42 duration_ms=95  error="CardDeclined: insufficient funds"
```

## Four outcomes

Every call ends in exactly one of them. You decide which exceptions are which, so there is no
bare `except Exception: pass` anywhere in your code.

| outcome | when | logged at | then |
|---|---|---|---|
| `finished` | the call returned | info (`level="debug"` for chatty calls) | the value is returned |
| `expected` | raised one of `expected=` | warning | re-raised for the caller |
| `swallowed` | raised one of `swallow=` | debug | `default=` is returned |
| `raised` | raised any other `Exception` | error, with traceback | the notifier is told, then re-raised |

A type listed in both `expected` and `swallow` counts as expected. `BaseException`s that are not
`Exception`s (`KeyboardInterrupt`, `SystemExit`, `asyncio.CancelledError`) pass through untouched
unless you list them. The re-raise is a bare `raise`, so tracebacks gain no frame from the decorator.

## Arguments

```python
@observed(
    "orders.ship",              # event root; the outcome is appended: orders.ship.finished
    expected=(OutOfStock,),     # normal operation, re-raised
    swallow=(KeyError,),        # "it wasn't there", replaced by default
    default=None,
    fields=("order_id",),       # argument names added to the log line and the event
    detail="carrier",           # one argument kept as a string on the event, not in the log context
    level="info",               # log level of `finished`
    notify_policy=POLICY,       # what a `raised` notification may carry (below)
)
```

`fields` and `detail` are resolved against the signature, so positional and keyword arguments both
work. `duration_ms` is measured with `perf_counter` and, for `async def`, covers the whole await.
Generators are refused at decoration time: the call returns before any work happens, so the timing
would mean nothing. Decorate the function that consumes the generator instead.

## Where the logger, sink and notifier come from

`observed` looks at the first argument (`self` for a method) for these attributes, and falls back
to a default when one is missing or has the wrong shape:

| attribute | expected shape | fallback |
|---|---|---|
| `log` | a structlog logger (has `.bind`) | `structlog.get_logger(module)` |
| `sink` | an `EventSink`: `emit(event)` | `NullSink`, which drops events |
| `notifier` | a `Notifier`: `error(title, text)` | none; nobody is told |
| `observe_context` | a mapping, e.g. `{"run_id": 7}` | `{}` |

`observe_context` is bound onto every log line and event from that instance. Plain functions get
the fallbacks, so `@observed` on a module-level function just logs.

## Events and sinks

Each outcome becomes an `ObservedEvent`:

```python
ObservedEvent(
    name="billing.charge",
    outcome=CallOutcome.EXPECTED,
    duration_ms=95,
    error="CardDeclined: insufficient funds",  # None when finished
    context={"customer_id": "c_42"},
    detail=None,
)
event.event  # "billing.charge.expected"
```

A sink is anything with `emit(event)`. Write one that increments a Prometheus counter, inserts a
row into a table, or pushes to a queue:

```python
class CountingSink:
    def __init__(self, counter):
        self.counter = counter

    def emit(self, event):
        self.counter.labels(event.name, event.outcome).inc()
```

## Testing with MemorySink

`MemorySink` keeps every event in a list, so tests assert on what happened instead of parsing logs:

```python
from observe_kit import CallOutcome, MemorySink


def test_declined_card_is_expected():
    sink = MemorySink()
    billing = Billing(log=structlog.get_logger(), sink=sink, notifier=None)

    with pytest.raises(CardDeclined):
        billing.charge("c_42", 500)

    [event] = sink.named("billing.charge")
    assert event.outcome is CallOutcome.EXPECTED
```

## Notifications and NotifyPolicy

On `raised`, the instance's notifier gets a title (`"billing.charge raised TimeoutError"`) and a
short text. Alerts end up in chat apps, phones and mailboxes, so the text is deliberately thin:

- only context fields you allow travel; the rest are counted, never shown;
- only the first line of the error travels; the lines after it are counted;
- URLs in that line are replaced by `<url withheld>`.

The default policy allows no fields. Set your own once and pass it where you decorate:

```python
from functools import partial
from observe_kit import NotifyPolicy, observed as _observed

POLICY = NotifyPolicy(
    fields=frozenset({"run_id", "count", "duration_ms"}),
    withheld_hint="see logs/app.jsonl",
)
observed = partial(_observed, notify_policy=POLICY)
```

```text
billing.charge raised TimeoutError

app.billing.Billing.charge
TimeoutError: Page.goto: Timeout 30000ms exceeded. (+2 line(s) withheld)
run_id=7 (1 field(s) withheld — see logs/app.jsonl)
```

The full error, traceback and context are still in the log line and the event; only the
notification is trimmed.

## Lineage

observe-kit is a rewrite of [atlassian-labs/observe](https://github.com/atlassian-labs/observe),
which I wrote at Atlassian in 2020. It keeps the idea and the Apache-2.0 license; the code is new.
See [NOTICE](NOTICE).

## License

[Apache-2.0](LICENSE)
