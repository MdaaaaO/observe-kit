"""The `observed` decorator."""

from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable, Mapping
from functools import wraps
from typing import Any, Literal, ParamSpec, TypeVar, cast

from .binding import bound as _bound_fields
from .config import defaults
from .events import CallOutcome, ObservedEvent
from .policy import DEFAULT_POLICY, NotifyPolicy
from .provider import Provider

P = ParamSpec("P")
R = TypeVar("R")

ExcTypes = tuple[type[BaseException], ...]


def observed(
    name: str,
    *,
    expected: ExcTypes = (),
    swallow: ExcTypes = (),
    default: Any = None,
    fields: tuple[str, ...] = (),
    detail: str | None = None,
    level: Literal["debug", "info"] = "info",
    notify_policy: NotifyPolicy | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Time a call, classify how it ended, log it and emit an event, on every invocation.

    Args:
        name: Event root, dotted, e.g. "billing.charge". The outcome is appended:
            "billing.charge.finished".
        expected: Exceptions that are a normal part of operating. Logged as a warning and
            **re-raised** for the caller to handle.
        swallow: Exceptions that mean "that thing wasn't there". Logged at debug and replaced by
            `default`. This is how `except Exception: pass` becomes explicit and visible.
        default: Returned when a `swallow` exception was caught.
        fields: Argument names to add to the event and the log line, e.g. ("user_id",).
            Resolved against the signature, so positional and keyword arguments both work.
        detail: One argument name whose value, as a string, becomes the event's `detail`. It is
            not added to the context: it is for a later query to read back, not for every log line.
        level: Log level of the FINISHED outcome. "debug" for chatty inner calls.
        notify_policy: What a RAISED notification may carry. When not given, the policy set with
            `configure()` applies, and failing that `DEFAULT_POLICY`, which allows no context
            fields; see `NotifyPolicy`.

    Anything that is an `Exception` and in neither tuple is RAISED: logged as an error with the
    traceback, sent to the instance's notifier if it has one, and re-raised. A type in both
    tuples counts as `expected`. `BaseException`s that are not `Exception`s (KeyboardInterrupt,
    SystemExit, asyncio.CancelledError) pass through untouched unless listed.

    Works on plain and `async def` functions and methods. Generators are refused, because the
    call returns before the work happens and the timing would be meaningless.

    Collaborators (logger, sink, notifier, context) come from the instance via `Provider`, with
    `configure()` supplying the sink and notifier an instance does not have.
    """

    def decorate(func: Callable[P, R]) -> Callable[P, R]:
        if inspect.isgeneratorfunction(func) or inspect.isasyncgenfunction(func):
            raise TypeError(
                f"@observed({name!r}) cannot wrap generator {func.__qualname__}: the call returns "
                "before the work happens. Observe the function that consumes it instead."
            )
        spec = _Spec(
            name=name,
            expected=expected,
            swallow=swallow,
            default=default,
            fields=fields,
            detail=detail,
            level=level,
            policy=notify_policy,
            sig=inspect.signature(func),
            module=func.__module__,
            qualname=f"{func.__module__}.{func.__qualname__}",
        )

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def awrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                call = _Call(spec, args, kwargs)
                try:
                    result = await cast(Awaitable[Any], func(*args, **kwargs))
                except BaseException as exc:
                    if not call.failed(exc):
                        raise
                    return spec.default
                call.finished()
                return result

            return cast(Callable[P, R], awrapper)

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            call = _Call(spec, args, kwargs)
            try:
                result = func(*args, **kwargs)
            except BaseException as exc:
                if not call.failed(exc):
                    raise
                return cast(R, spec.default)
            call.finished()
            return result

        return wrapper

    return decorate


class _Spec:
    """Everything fixed at decoration time."""

    __slots__ = (
        "name",
        "expected",
        "swallow",
        "default",
        "fields",
        "detail",
        "level",
        "policy",
        "sig",
        "module",
        "qualname",
    )

    def __init__(
        self,
        *,
        name: str,
        expected: ExcTypes,
        swallow: ExcTypes,
        default: Any,
        fields: tuple[str, ...],
        detail: str | None,
        level: str,
        policy: NotifyPolicy | None,
        sig: inspect.Signature,
        module: str,
        qualname: str,
    ) -> None:
        self.name = name
        self.expected = expected
        self.swallow = swallow
        self.default = default
        self.fields = fields
        self.detail = detail
        self.level = level
        self.policy = policy
        self.sig = sig
        self.module = module
        self.qualname = qualname


class _Call:
    """One invocation: collaborators resolved, clock started. Sync and async share it."""

    __slots__ = ("spec", "args", "log", "sink", "context", "detail", "started")

    def __init__(self, spec: _Spec, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self.spec = spec
        self.args = args
        self.sink = Provider.sink(args)
        bound = _bound(spec.sig, args, kwargs)
        self.context = _context(spec.fields, Provider.context(args), bound)
        self.detail = _detail(spec.detail, bound)
        self.log = Provider.logger(args, spec.module).bind(**self.context)
        self.started = time.perf_counter()

    def finished(self) -> None:
        ev = self._event(CallOutcome.FINISHED, None)
        getattr(self.log, self.spec.level)(ev.event, duration_ms=ev.duration_ms)
        self.sink.emit(ev)

    def failed(self, exc: BaseException) -> bool:
        """Record `exc`, from inside the `except` block. True when it is swallowed; the caller
        re-raises otherwise, with a bare `raise`, so the traceback gains no frame from here."""
        spec = self.spec
        if isinstance(exc, spec.expected):
            ev = self._event(CallOutcome.EXPECTED, exc)
            self.log.warning(ev.event, duration_ms=ev.duration_ms, error=ev.error)
            self.sink.emit(ev)
            return False
        if isinstance(exc, spec.swallow):
            ev = self._event(CallOutcome.SWALLOWED, exc)
            self.log.debug(
                ev.event, duration_ms=ev.duration_ms, error=ev.error, default=spec.default
            )
            self.sink.emit(ev)
            return True
        if not isinstance(exc, Exception):
            return False
        ev = self._event(CallOutcome.RAISED, exc)
        self.log.error(ev.event, duration_ms=ev.duration_ms, error=ev.error, exc_info=True)
        self.sink.emit(ev)
        notifier = Provider.notifier(self.args)
        if notifier is not None:
            notifier.error(
                title=f"{spec.name} raised {type(exc).__name__}",
                text=_policy(spec).text(spec.qualname, ev.error, self.context),
            )
        return False

    def _event(self, outcome: CallOutcome, exc: BaseException | None) -> ObservedEvent:
        # perf_counter, then round: truncating to whole seconds first would report 0 ms for
        # anything under a second.
        duration_ms = round((time.perf_counter() - self.started) * 1000)
        error = f"{type(exc).__name__}: {exc}" if exc is not None else None
        return ObservedEvent(self.spec.name, outcome, duration_ms, error, self.context, self.detail)


def _policy(spec: _Spec) -> NotifyPolicy:
    """The decorator's policy, else the configured one, else DEFAULT_POLICY; read per call."""
    if spec.policy is not None:
        return spec.policy
    configured = defaults().notify_policy
    return configured if configured is not None else DEFAULT_POLICY


def _bound(
    sig: inspect.Signature, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> Mapping[str, Any]:
    """The call's arguments by name, which `fields` and `detail` are resolved against."""
    try:
        return sig.bind_partial(*args, **kwargs).arguments
    except TypeError:  # the call itself is malformed; let func() raise the real error
        return {}


def _context(
    fields: tuple[str, ...], base: Mapping[str, object], bound: Mapping[str, Any]
) -> dict[str, object]:
    ctx: dict[str, object] = {**_bound_fields(), **base}
    for f in fields:
        if f in bound:
            ctx[f] = bound[f]
    return ctx


def _detail(name: str | None, bound: Mapping[str, Any]) -> str | None:
    value = bound.get(name) if name is not None else None
    return None if value is None else str(value)
