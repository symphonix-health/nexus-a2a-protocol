import os
import sys
import importlib


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def test_retry_succeeds_after_failures():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "retry")

    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("fail")
        return "ok"

    sleeper_calls = []

    def sleeper(t: float) -> None:
        sleeper_calls.append(t)

    out = m.retry(fn, retries=3, base_delay=0.01, sleeper=sleeper)
    assert out == "ok"
    # Should have slept twice (after 1st and 2nd failure)
    assert len(sleeper_calls) == 2
    assert sleeper_calls[0] < sleeper_calls[1]


def test_retry_exhausts_and_raises():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "retry")

    def bad():
        raise ValueError("nope")

    try:
        m.retry(bad, retries=2, base_delay=0.0, sleeper=lambda x: None)
    except ValueError as e:
        assert "nope" in str(e)
    else:
        assert False, "expected ValueError"
