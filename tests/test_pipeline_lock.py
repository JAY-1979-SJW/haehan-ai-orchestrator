import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ops import pipeline_lock as pl


def test_acquire_busy_and_release(tmp_path):
    tok = pl.acquire("t", root=tmp_path, log_path="x.log")
    with pytest.raises(pl.LockBusy) as e:
        pl.acquire("t", root=tmp_path)
    assert "x.log" in str(e.value)
    assert pl.live_lock("t", tmp_path)
    pl.release("t", tok, tmp_path)
    assert pl.live_lock("t", tmp_path) is None


def test_token_reentry(tmp_path, monkeypatch):
    tok = pl.acquire("t", root=tmp_path)
    monkeypatch.setenv(pl.TOKEN_ENV, tok)
    assert pl.acquire("t", root=tmp_path) == tok
    pl.release("t", tok, tmp_path)


def test_stale_recovered(tmp_path):
    p = pl.lock_path("t", tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text('{"pid": 99999999, "proc_create_time": 1, "token": "z"}', encoding="utf-8")
    tok = pl.acquire("t", root=tmp_path)
    assert pl.read_lock(p)["token"] == tok
    pl.release("t", tok, tmp_path)


def test_guard_hook_denies(tmp_path, monkeypatch):
    from scripts.ops import guard_single_verify as g

    monkeypatch.setattr(g, "live_lock", lambda n: {"pid": 1, "log_path": "L.log"} if n == "verify" else None)
    assert "L.log" in g.decide("python scripts/ops/verify_change.py --base master")
    assert g.decide("python scripts/ops/merge_stage.py x") is None
    assert g.decide("ls") is None


def test_guard_hook_cli_noop():
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run(
        [sys.executable, str(root / "scripts/ops/guard_single_verify.py")],
        input='{"tool_name":"Bash","tool_input":{"command":"ls"}}',
        capture_output=True,
        text=True,
        env={**os.environ},
    )
    assert r.returncode == 0 and r.stdout == ""
