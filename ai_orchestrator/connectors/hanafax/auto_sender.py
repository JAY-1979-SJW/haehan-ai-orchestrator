"""L3 커넥터 — 하나팩스 자동 발송용 발송기 어댑터 (기존 `scripts.hanafax.sender.send_fax` 를 호출만 한다).

기준서: docs/specs/2026-10-02_hanafax_auto_send.md

- 워크플로(`auto_send`)는 발송기를 주입받는다. 이 모듈이 운영용 발송기를 만든다.
- **발송 직전에 첨부 문서의 해시를 승인서의 `document_hash` 와 다시 비교한다.** 승인 뒤에 파일이 바뀌었으면 발송기를 만들지 않는다.
- `send_fax` 의 결과 중 **요청이 나가기 전에 확정된 실패**(자격증명·번호·첨부·로그인·페이지 이동)만 `definite_failure` 로 알린다.
  그 외 실패 메시지(타임아웃·결과 불명확 등)는 요청이 나갔을 수 있으므로 알리지 않는다 → 워크플로가 `unknown` 으로 멈춘다.
- 엔진(`scripts/hanafax/sender.py`)은 수정하지 않는다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

# 워크플로의 `Sender` 와 같은 모양 (L3 → L6 import 는 역방향이라 여기서 따로 선언한다)
Sender = Callable[[str, str, str], dict[str, Any]]
BulkSender = Callable[[list[dict[str, str]], str], dict[str, Any]]

# send_fax 가 "팩스보내기" 버튼을 누르기 전에 돌려주는 실패 메시지의 시작 문구 (scripts/hanafax/sender.py 와 맞춘다)
_PRE_SEND_FAILURES = (
    "자격증명 없음",
    "playwright 미설치",
    "팩스번호 오류",
    "첨부파일 없음",
    "허용되지 않은 첨부파일 형식",
    "로그인 실패",
    "팩스 페이지 이동 실패",
    "팩스번호 추가 실패",
    "TIF 변환 실패",
    "첨부파일 미지정",
)


class DocumentChanged(ValueError):
    """승인 뒤에 문서가 바뀌었거나 읽을 수 없다 — 발송하지 않는다."""


def file_sha256(path: str) -> str:
    """첨부 문서 내용의 SHA-256. 승인서 생성 때와 발송 직전에 같은 함수로 계산한다."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_document(path: str) -> str:
    """허용 형식(pdf/docx/doc)의 존재하는 파일인지 확인하고 오류 문구를 돌려준다(정상이면 빈 문자열)."""
    from scripts.hanafax.sender import _validate_attach_file

    return _validate_attach_file(path) or ""


def is_pre_send_failure(result: dict[str, Any]) -> bool:
    message = str(result.get("message", ""))
    return not result.get("success") and not result.get("job_id") and message.startswith(_PRE_SEND_FAILURES)


def _check_document(document_ref: str, expected_document_hash: str) -> None:
    error = validate_document(document_ref)
    if error:
        raise DocumentChanged(error)
    if file_sha256(document_ref) != expected_document_hash:
        raise DocumentChanged("승인 뒤에 문서 내용이 바뀌었습니다 — 새 승인서가 필요합니다")


def _changed_result(document_ref: str, expected_document_hash: str) -> dict[str, Any] | None:
    """전송 직전 재검증. 바뀌었으면 '요청 전 명확한 실패' 결과를 돌려준다(전송하지 않음)."""
    try:
        _check_document(document_ref, expected_document_hash)
    except (DocumentChanged, OSError) as exc:
        return {"success": False, "job_id": None, "definite_failure": True, "message": f"문서 검증 실패로 전송 중단: {exc}"}
    return None


def build_sender(document_ref: str, expected_document_hash: str) -> Sender:
    """승인된 문서 하나를 보내는 발송기를 만든다. 문서가 승인 때와 다르면 `DocumentChanged`."""
    _check_document(document_ref, expected_document_hash)

    def _send(number: str, name: str, subject: str) -> dict[str, Any]:
        from scripts.hanafax.sender import send_fax

        if (changed := _changed_result(document_ref, expected_document_hash)) is not None:
            return changed  # 승인 뒤 파일이 바뀌었다 — 건마다 다시 확인한다(시간차 교체 방지)

        result = send_fax(receiver_fax=number, subject=subject, body="", receiver_name=name, attach_file=document_ref)
        if is_pre_send_failure(result):
            result = {**result, "definite_failure": True}
        return result

    return _send


def build_bulk_sender(document_ref: str, expected_document_hash: str) -> BulkSender:
    """승인된 문서 하나를 여러 번호에 단체발송하는 발송기(하나팩스 단체발송: 로그인·업로드 1회). 문서가 바뀌었으면 `DocumentChanged`."""
    _check_document(document_ref, expected_document_hash)

    def _send(recipients: list[dict[str, str]], subject: str) -> dict[str, Any]:
        from scripts.hanafax.sender import send_fax_bulk

        if (changed := _changed_result(document_ref, expected_document_hash)) is not None:
            return changed

        result = send_fax_bulk(
            [{"receiver_fax": r["fax"], "receiver_name": r.get("name", "")} for r in recipients],
            subject,
            attach_file=document_ref,
        )
        if is_pre_send_failure(result):
            result = {**result, "definite_failure": True}
        return result

    return _send
