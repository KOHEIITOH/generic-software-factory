"""Optional local cancellation checkpoint; no transport or permission semantics."""
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar

_CONTROL: ContextVar[Callable[[], None] | None] = ContextVar('operation_control', default=None)


class OperationStopped(RuntimeError):
    pass


def checkpoint() -> None:
    if control := _CONTROL.get():
        control()


@contextmanager
def operation_control(control: Callable[[], None]):
    token = _CONTROL.set(control)
    try:
        yield
    finally:
        _CONTROL.reset(token)
