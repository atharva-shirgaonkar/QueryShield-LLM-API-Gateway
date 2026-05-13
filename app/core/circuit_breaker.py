"""Circuit breaker utilities for protecting external service calls."""

import inspect
import time
from collections.abc import Awaitable
from enum import Enum
from typing import TypeVar


T = TypeVar("T")


class CircuitBreakerState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(Exception):
    """Raised when a protected call is blocked by an open circuit."""


class CircuitBreaker:
    """Track failures and block calls while a downstream service recovers."""

    CLOSED = CircuitBreakerState.CLOSED
    OPEN = CircuitBreakerState.OPEN
    HALF_OPEN = CircuitBreakerState.HALF_OPEN

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        success_threshold: int = 2,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.opened_at: float | None = None
        self._trial_in_progress = False

    async def call(self, coroutine: Awaitable[T]) -> T:
        """Run an async call if the circuit allows it, tracking the outcome."""
        if not self._can_call():
            self._close_coroutine(coroutine)
            raise CircuitBreakerOpenError("Circuit breaker is open")

        try:
            result = await coroutine
        except Exception:
            self._record_failure()
            raise

        self._record_success()
        return result

    def _can_call(self) -> bool:
        now = time.monotonic()

        if self.state == CircuitBreakerState.OPEN:
            if self.opened_at is None:
                return False

            if now - self.opened_at >= self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                self._trial_in_progress = False
            else:
                return False

        if self.state == CircuitBreakerState.HALF_OPEN:
            if self._trial_in_progress:
                return False
            self._trial_in_progress = True

        return True

    def _record_success(self) -> None:
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            self._trial_in_progress = False
            if self.success_count >= self.success_threshold:
                self._close()
            return

        self.failure_count = 0

    def _record_failure(self) -> None:
        if self.state == CircuitBreakerState.HALF_OPEN:
            self._trial_in_progress = False
            self._open()
            return

        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self._open()

    def _open(self) -> None:
        self.state = CircuitBreakerState.OPEN
        self.failure_count = self.failure_threshold
        self.success_count = 0
        self.opened_at = time.monotonic()
        self._trial_in_progress = False

    def _close(self) -> None:
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.opened_at = None
        self._trial_in_progress = False

    @staticmethod
    def _close_coroutine(coroutine: Awaitable[T]) -> None:
        if inspect.iscoroutine(coroutine):
            coroutine.close()
