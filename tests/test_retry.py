"""Tests for the retry/backoff policy (Stage 2.1)."""

import httpx
import pytest
from plane.errors import HttpError

from plane_mcp import retry as R


@pytest.fixture
def no_sleep():
    calls = []
    yield calls, lambda d: calls.append(d)


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    monkeypatch.setenv("PLANE_MAX_RETRIES", "3")
    monkeypatch.setenv("PLANE_RETRY_BASE_DELAY", "0.01")


def _counter(exc_factory, succeed_after):
    state = {"n": 0}

    def fn():
        state["n"] += 1
        if state["n"] < succeed_after:
            raise exc_factory()
        return "ok"

    return fn, state


def test_is_read_only_operation():
    assert R.is_read_only_operation("work_items.list")
    assert R.is_read_only_operation("projects.get_members")
    assert R.is_read_only_operation("cycles.retrieve")
    assert not R.is_read_only_operation("work_items.create")
    assert not R.is_read_only_operation("work_items.update")


def test_503_retried_for_write(no_sleep):
    calls, sleep = no_sleep
    fn, state = _counter(lambda: HttpError("busy", 503), succeed_after=3)
    assert R.call_with_retries(fn, "work_items.create", read_only=False, sleep=sleep) == "ok"
    assert state["n"] == 3
    assert len(calls) == 2


def test_429_retried_for_write(no_sleep):
    calls, sleep = no_sleep
    fn, state = _counter(lambda: HttpError("rate", 429), succeed_after=2)
    assert R.call_with_retries(fn, "work_items.update", read_only=False, sleep=sleep) == "ok"
    assert state["n"] == 2


def test_504_not_retried_for_write(no_sleep):
    calls, sleep = no_sleep
    fn, state = _counter(lambda: HttpError("gateway", 504), succeed_after=99)
    with pytest.raises(HttpError):
        R.call_with_retries(fn, "work_items.create", read_only=False, sleep=sleep)
    assert state["n"] == 1
    assert calls == []


def test_504_retried_for_read(no_sleep):
    calls, sleep = no_sleep
    fn, state = _counter(lambda: HttpError("gateway", 504), succeed_after=2)
    assert R.call_with_retries(fn, "work_items.list", read_only=True, sleep=sleep) == "ok"
    assert state["n"] == 2


def test_404_never_retried(no_sleep):
    calls, sleep = no_sleep
    fn, state = _counter(lambda: HttpError("missing", 404), succeed_after=99)
    with pytest.raises(HttpError):
        R.call_with_retries(fn, "work_items.list", read_only=True, sleep=sleep)
    assert state["n"] == 1


def test_connect_error_retried_for_write(no_sleep):
    calls, sleep = no_sleep
    fn, state = _counter(lambda: httpx.ConnectError("refused"), succeed_after=2)
    assert R.call_with_retries(fn, "work_items.create", read_only=False, sleep=sleep) == "ok"
    assert state["n"] == 2


def test_read_timeout_not_retried_for_write(no_sleep):
    calls, sleep = no_sleep
    fn, state = _counter(lambda: httpx.ReadTimeout("slow"), succeed_after=99)
    with pytest.raises(httpx.ReadTimeout):
        R.call_with_retries(fn, "work_items.create", read_only=False, sleep=sleep)
    assert state["n"] == 1


def test_retries_exhausted_reraises_last(no_sleep):
    calls, sleep = no_sleep
    fn, state = _counter(lambda: HttpError("busy", 503), succeed_after=99)
    with pytest.raises(HttpError):
        R.call_with_retries(fn, "work_items.list", read_only=True, sleep=sleep)
    # 1 initial + 3 retries
    assert state["n"] == 4
    assert len(calls) == 3


def test_max_retries_zero_means_single_attempt(monkeypatch, no_sleep):
    monkeypatch.setenv("PLANE_MAX_RETRIES", "0")
    calls, sleep = no_sleep
    fn, state = _counter(lambda: HttpError("busy", 503), succeed_after=99)
    with pytest.raises(HttpError):
        R.call_with_retries(fn, "work_items.list", read_only=True, sleep=sleep)
    assert state["n"] == 1
