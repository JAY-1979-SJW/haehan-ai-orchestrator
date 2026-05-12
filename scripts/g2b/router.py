"""G2B (나라장터/조달청) 서비스 라우터."""
from __future__ import annotations

from scripts.gate import check as gate_check
from scripts.logger import get_logger

__status__ = {
    "tasks": {
        "discover (공개공고 URL 탐색)": "partial",
        "download (첨부파일 다운로드)": "partial",
        "suite (Read-Only 라이브)":     "partial",
    },
    "note": "라우터 연결 완료. 실제 스크립트(discover/download/suite) 검증 필요",
}

_log = get_logger(__name__)


def run_g2b(task: str | None, sub: str | None, args: list[str]) -> None:
    """G2B 서비스 라우팅.

    task: discover | download | suite
    """
    match task or "help":
        case "discover":
            _cmd_discover(args)
        case "download":
            _cmd_download(args)
        case "suite":
            _cmd_suite(args)
        case _:
            _print_help()


def _cmd_discover(args: list[str]) -> None:
    gate_check("goto")
    print("[G2B] 공개 공고 유효 URL 탐색")
    from scripts.g2b.discover_valid_public_notice_urls import main
    main()


def _cmd_download(args: list[str]) -> None:
    gate_check("file_delete")  # 파일 다운로드 = notify
    print("[G2B] 첨부파일 배치 다운로드")
    from scripts.g2b.download_g2b_direct_attachment_urls import main
    main()


def _cmd_suite(args: list[str]) -> None:
    gate_check("goto")
    print("[G2B] 공개 공고 Read-Only 라이브 스위트 실행")
    from scripts.g2b.run_public_notice_readonly_live_suite import main
    main()


def _print_help() -> None:
    print("""G2B 사용법:
  python scripts/cdp_client.py g2b discover    공개 공고 URL 탐색
  python scripts/cdp_client.py g2b download    첨부파일 배치 다운로드
  python scripts/cdp_client.py g2b suite       Read-Only 라이브 스위트""")
