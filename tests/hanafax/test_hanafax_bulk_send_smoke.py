"""scripts/hanafax/bulk_send.py 스모크 — send_bulk_batch 실호출 없음."""

from __future__ import annotations

import json

import pytest

from scripts.hanafax import bulk_send as bs
from scripts.hanafax.router import run_hanafax


def test_import_constants():
    assert bs.BULK_PAGE.startswith(bs.BASE_URL)


def test_load_batch_roundtrip_and_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "BATCH_DIR", tmp_path)
    (tmp_path / "batch_01.json").write_text(json.dumps({"fax_numbers": ["0212345678"]}), encoding="utf-8")
    assert bs.load_batch(1)["fax_numbers"] == ["0212345678"]
    with pytest.raises(FileNotFoundError):
        bs.load_batch(2)


def test_save_result_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "RESULT_DIR", tmp_path / "res")
    bs.save_result(3, {"ok": True, "한글": "값"})
    files = list((tmp_path / "res").glob("bulk_batch_03_*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text(encoding="utf-8")) == {"ok": True, "한글": "값"}


def test_get_creds_delegates_empty(monkeypatch):
    import scripts.hanafax.auth as auth

    monkeypatch.setattr(auth, "get_credentials", lambda: ("", ""))
    assert bs._get_creds() == ("", "")


def test_send_bulk_batch_missing_file_no_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "FAX_FILE", tmp_path / "none.xlsx")
    assert bs.send_bulk_batch(1, ["1"])["ok"] is False


def test_send_bulk_batch_dry_run_no_browser(tmp_path, monkeypatch):
    f = tmp_path / "f.xlsx"
    f.write_bytes(b"x")
    monkeypatch.setattr(bs, "FAX_FILE", f)
    res = bs.send_bulk_batch(1, ["1", "2"], dry_run=True)
    assert res["dry_run"] is True and res["count"] == 2


def test_router_help_on_unknown_task(capsys):
    run_hanafax("nonsense", None, [])
    out = capsys.readouterr().out
    assert "하나팩스 명령" in out and "batch-send" in out
