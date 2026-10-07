"""scripts/instagram/api_publish.py 스모크 — 외부 호출 0."""

from __future__ import annotations

import pytest

from scripts.instagram import api_publish as ap


@pytest.fixture()
def calls(monkeypatch):
    log: list = []
    monkeypatch.setattr(ap, "_creds", lambda: ("tok", "uid"))

    def fake_post(path, params):
        log.append(("post", path, params))
        return {"id": "C1"}

    monkeypatch.setattr(ap, "_post", fake_post)
    monkeypatch.setattr(ap, "wait_ready", lambda cid: log.append(("wait", cid)))
    return log


def test_import_constants():
    assert ap.GRAPH.startswith("https://graph.instagram.com/")
    assert ap.POLL_MAX > 0


def test_publish_reel_unconfirmed_does_not_publish(calls):
    res = ap.publish_reel("https://x/v.mp4", "cap")
    assert res == {"container_id": "C1", "published": False}
    assert not any(c[0] == "post" and c[1].endswith("media_publish") for c in calls)


def test_publish_reel_confirmed_order_and_params(calls):
    from scripts.common.gate import CONFIRM_TEXTS

    res = ap.publish_reel("https://x/v.mp4", "cap", confirmed=True, approval=CONFIRM_TEXTS["instagram_publish"])
    assert res["published"] is True and res["container_id"] == "C1"
    assert [c[0] for c in calls] == ["post", "wait", "post"]
    assert calls[0][1] == "uid/media"
    assert calls[0][2]["media_type"] == "REELS" and calls[0][2]["video_url"] == "https://x/v.mp4"
    assert calls[2][1] == "uid/media_publish" and calls[2][2] == {"creation_id": "C1"}


def test_container_failure_raises(monkeypatch):
    monkeypatch.setattr(ap, "_creds", lambda: ("t", "u"))
    monkeypatch.setattr(ap, "_post", lambda p, q: {})
    with pytest.raises(RuntimeError):
        ap.create_reel_container("v", "c")


def test_creds_missing_raises(monkeypatch):
    monkeypatch.setattr(ap, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("IG_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("IG_USER_ID", raising=False)
    with pytest.raises(RuntimeError):
        ap._creds()


def test_wait_ready_error_and_finished(monkeypatch):
    monkeypatch.setattr(ap, "_get", lambda p, q: {"status_code": "ERROR"})
    with pytest.raises(RuntimeError):
        ap.wait_ready("C1")
    monkeypatch.setattr(ap, "_get", lambda p, q: {"status_code": "FINISHED"})
    assert ap.wait_ready("C1") is None


def test_carousel_bounds(monkeypatch):
    monkeypatch.setattr(ap, "_creds", lambda: ("t", "u"))
    with pytest.raises(ValueError):
        ap.create_carousel(["a"], "c")
