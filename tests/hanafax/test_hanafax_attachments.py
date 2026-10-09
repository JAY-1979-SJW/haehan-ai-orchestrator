"""하나팩스 첨부 파일 — 올리기·검사·정리·API. 사이트에는 접속하지 않는다."""

from __future__ import annotations

import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_orchestrator.connectors.hanafax import attachments as att
from ai_orchestrator.connectors.hanafax import authorization_service as service
from ai_orchestrator.connectors.hanafax import authorization_store as store
from ai_orchestrator.connectors.hanafax.router import hanafax_router
from tools.gates.auth import get_current_user

PDF = b"%PDF-1.4 sample"
DOCX = b"PK\x03\x04 sample"
DOC = b"\xd0\xcf\x11\xe0 sample"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DB_PATH", tmp_path / "fax_authorizations.db")
    monkeypatch.setattr(att, "_UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(service, "_allowed_roots", lambda: [tmp_path.resolve()])  # 임시 폴더를 허용 폴더로
    monkeypatch.setattr(service, "_BLOCKED_PARTS", {".ssh"})  # AppData 아래 임시 폴더 때문에 기본 차단 목록은 푼다


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(hanafax_router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: {"actor": "tester", "role": "owner"}
    return TestClient(app)


# ── 검사 ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("name", "data"), [("a.pdf", PDF), ("b.docx", DOCX), ("c.doc", DOC), ("D.PDF", PDF)])
def test_inspect_accepts_allowed_formats(tmp_path, name, data):
    f = tmp_path / name
    f.write_bytes(data)
    assert att.inspect_file(f)["name"] == name


@pytest.mark.parametrize(
    ("name", "data", "message"),
    [
        ("a.txt", b"hello", "허용되지 않는"),
        ("noext", PDF, "허용되지 않는"),
        ("fake.pdf", b"not a pdf at all", "형식이 아닙니다"),  # 이름만 pdf
        ("fake.docx", PDF, "형식이 아닙니다"),
        ("empty.pdf", b"", "빈 파일"),
    ],
)
def test_inspect_rejects_bad_files(tmp_path, name, data, message):
    f = tmp_path / name
    f.write_bytes(data)
    with pytest.raises(ValueError, match=message):
        att.inspect_file(f)


def test_inspect_rejects_missing_and_oversize(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        att.inspect_file(tmp_path / "none.pdf")
    monkeypatch.setattr(att, "MAX_BYTES", 10)
    f = tmp_path / "big.pdf"
    f.write_bytes(PDF + b"x" * 50)
    with pytest.raises(ValueError, match="너무 큽니다"):
        att.inspect_file(f)


# ── 올리기 ────────────────────────────────────────────────────────────────────


def test_save_upload_stores_inside_app_dir_with_sanitized_name(tmp_path):
    saved = att.save_upload("../../evil/공문 (최종)!.pdf", PDF)
    from pathlib import Path

    p = Path(saved["path"])
    assert p.parent == (tmp_path / "uploads").resolve() and p.is_file()  # 경로 조작은 이름만 남는다
    assert ".." not in p.name and "/" not in p.name and p.suffix == ".pdf" and "공문" in p.name
    again = att.save_upload("../../evil/공문 (최종)!.pdf", PDF)
    assert again["path"] != saved["path"]  # 같은 이름이어도 덮어쓰지 않는다


@pytest.mark.parametrize("name", ["x.exe", "x.pdf.exe", "", "...", "x"])
def test_save_upload_rejects_bad_names(name):
    with pytest.raises(ValueError, match="허용되지 않는"):
        att.save_upload(name, PDF)


def test_save_upload_removes_file_that_fails_content_check(tmp_path):
    with pytest.raises(ValueError, match="형식이 아닙니다"):
        att.save_upload("fake.pdf", b"MZ executable disguised")
    assert list((tmp_path / "uploads").glob("*")) == []  # 검사에 실패한 파일은 남기지 않는다


def test_save_upload_rejects_oversize_without_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(att, "MAX_BYTES", 10)
    with pytest.raises(ValueError, match="너무 큽니다"):
        att.save_upload("big.pdf", PDF + b"x" * 100)
    assert not (tmp_path / "uploads").exists() or list((tmp_path / "uploads").glob("*")) == []


# ── 정리 ──────────────────────────────────────────────────────────────────────


def test_purge_removes_only_old_unreferenced_uploads():
    old_unref = att.save_upload("old.pdf", PDF)["path"]
    old_ref = att.save_upload("keep.pdf", PDF)["path"]
    recent = att.save_upload("new.pdf", PDF)["path"]
    long_ago = time.time() - 40 * 86400
    for p in (old_unref, old_ref):
        os.utime(p, (long_ago, long_ago))
    assert att.purge_old({old_ref}) == 1
    assert not os.path.exists(old_unref) and os.path.exists(old_ref) and os.path.exists(recent)


# ── 서비스: 경로 확인·승인서 생성 ─────────────────────────────────────────────────


def test_check_attachment_applies_same_rules_as_create(tmp_path):
    good = tmp_path / "공문.pdf"
    good.write_bytes(PDF)
    info = service.check_attachment(str(good))
    assert info["name"] == "공문.pdf" and info["path"] == str(good.resolve())
    for bad, message in (
        ("상대/경로.pdf", "절대"),
        (str(tmp_path / "none.pdf"), "찾을 수 없"),
        ("\\\\host\\share\\x.pdf", "UNC"),
    ):
        with pytest.raises(ValueError, match=message):
            service.check_attachment(bad)
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"plain text")
    with pytest.raises(ValueError, match="형식이 아닙니다"):
        service.check_attachment(str(fake))
    outside = tmp_path.parent / "outside.pdf"
    outside.write_bytes(PDF)
    try:
        with pytest.raises(ValueError, match="허용된 폴더"):
            service.check_attachment(str(outside))
    finally:
        outside.unlink(missing_ok=True)


def test_create_rejects_renamed_file(tmp_path):
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"plain text")
    with pytest.raises(ValueError, match="형식이 아닙니다"):
        service.create(
            {
                "name": "n",
                "subject": "s",
                "document_ref": str(fake),
                "recipients": [{"fax": "02-111-2222", "name": ""}],
            },
            user="u",
        )


def test_uploaded_file_can_be_used_for_a_draft():
    saved = service.upload_attachment("공문.pdf", PDF)
    row = service.create(
        {
            "name": "n",
            "subject": "s",
            "document_ref": saved["path"],
            "recipients": [{"fax": "02-111-2222", "name": ""}],
        },
        user="u",
    )
    assert row["document_ref"] == saved["path"] and not row["approved"]


# ── API ──────────────────────────────────────────────────────────────────────


def test_api_upload_and_check(client):
    ok = client.post("/api/v1/hanafax/attachments", files={"file": ("공문.pdf", PDF, "application/pdf")})
    assert ok.status_code == 200 and ok.json()["name"].endswith("공문.pdf") and ok.json()["size"] == len(PDF)
    checked = client.post("/api/v1/hanafax/attachments/check", json={"path": ok.json()["path"]})
    assert checked.status_code == 200 and checked.json()["path"] == ok.json()["path"]


@pytest.mark.parametrize(
    ("filename", "data", "message"),
    [("evil.exe", b"MZ", "허용되지 않는"), ("fake.pdf", b"nothing", "형식이 아닙니다")],
)
def test_api_upload_rejects_bad_files(client, filename, data, message):
    r = client.post("/api/v1/hanafax/attachments", files={"file": (filename, data, "application/octet-stream")})
    assert r.status_code == 400 and message in r.json()["detail"]


def test_api_upload_reads_at_most_limit_plus_one(client, monkeypatch):
    monkeypatch.setattr(att, "MAX_BYTES", 100)
    r = client.post("/api/v1/hanafax/attachments", files={"file": ("big.pdf", PDF + b"x" * 5000, "application/pdf")})
    assert r.status_code == 400 and "너무 큽니다" in r.json()["detail"]


def test_api_check_rejects_bad_path(client):
    r = client.post("/api/v1/hanafax/attachments/check", json={"path": "상대/경로.pdf"})
    assert r.status_code == 400 and "절대" in r.json()["detail"]
