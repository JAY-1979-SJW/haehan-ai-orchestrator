"""collect_google_passwords_list 안전화 검증 — 실제 브라우저/9222/외부 접속 없음(가짜 페이지 사용)."""

from __future__ import annotations

import importlib
import json

MOD = "scripts.auth.collect_google_passwords_list"


class FakePage:
    url = "https://passwords.google.com/password/x"

    def goto(self, *a, **k):
        pass

    def evaluate(self, js, *a):
        if "scrollHeight" in js:
            return 1
        if "a[href]" in js:
            return ["https://passwords.google.com/password/1"]
        return ["클립보드에 사용자 이름 alice@example.com 복사"]

    def inner_text(self, sel):
        return "x\ny\nexample.com\n"


def _mod(monkeypatch):
    mod = importlib.import_module(MOD)
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)
    return mod


def test_import_has_no_side_effect():
    mod = importlib.import_module(MOD)
    assert callable(mod.main)


def test_default_is_dry_run_without_connect(monkeypatch, capsys):
    mod = _mod(monkeypatch)

    def boom(*a, **k):
        raise AssertionError("접속 시도 금지")

    monkeypatch.setattr(mod, "collect", boom)
    assert mod.main([]) == 0
    assert "dry-run" in capsys.readouterr().out


def test_execute_no_password_key_and_masked(monkeypatch, tmp_path, capsys):
    mod = _mod(monkeypatch)
    out = tmp_path / "o.json"
    monkeypatch.setattr(mod, "OUT_FILE", out)
    monkeypatch.setattr(mod, "collect", lambda mask_email=True: mod.collect_from_page(FakePage(), mask_email))
    assert mod.main(["--execute"]) == 0
    assert "9222" in capsys.readouterr().out
    text = out.read_text(encoding="utf-8")
    data = json.loads(text)
    assert all(set(r) == {"site", "username"} for r in data["records"])
    assert "password" not in text.lower()
    assert data["records"][0]["username"] == "al***@example.com"


def test_write_output_strips_password_keys(tmp_path, capsys):
    mod = importlib.import_module(MOD)
    out = tmp_path / "o.json"
    assert mod.write_output([{"site": "a.com", "username": "u", "password": "zzz"}], out) == 1
    assert "zzz" not in out.read_text(encoding="utf-8")
    assert "경고" in capsys.readouterr().out


def test_mask_username():
    mod = importlib.import_module(MOD)
    assert mod.mask_username("bob@x.com") == "bo***@x.com"
    assert mod.mask_username("plainid") == "plainid"
