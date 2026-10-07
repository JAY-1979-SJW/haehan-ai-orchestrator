"""navigator_common — 공유 상수·유틸리티 (다른 navigator_* leaf가 import 가능)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SESSION_BACKUP_DIR = ROOT / "data" / "browser_sessions" / "backups"

# 도메인 별칭 → URL
ALIAS: dict[str, str] = {
    # 네이버
    "naver": "https://www.naver.com/",
    "naver-blog": "https://blog.naver.com/",
    "naver-mail": "https://mail.naver.com/",
    "naver-cafe": "https://cafe.naver.com/",
    "blog": "https://blog.naver.com/",
    # 구글
    "google": "https://www.google.com/",
    "google-account": "https://myaccount.google.com/",
    "google-console": "https://console.cloud.google.com/",
    "google-credentials": "https://console.cloud.google.com/apis/credentials",
    "google-oauth-credentials": "https://console.cloud.google.com/apis/credentials",
    "gmail": "https://mail.google.com/",
    "calendar": "https://calendar.google.com/",
    "drive": "https://drive.google.com/",
    "docs": "https://docs.google.com/",
    "sheets": "https://sheets.google.com/",
    "slides": "https://slides.google.com/",
    "youtube": "https://www.youtube.com/",
    # 카카오/다음
    "kakao": "https://www.kakaocorp.com/",
    "kakao-dev": "https://developers.kakao.com/",
    "daum": "https://www.daum.net/",
    # 기타
    "tistory": "https://www.tistory.com/",
    "github": "https://github.com/",
}


def resolve(target: str) -> str:
    """별칭 또는 URL을 정규 URL로 변환."""
    t = target.strip().lower()
    if t in ALIAS:
        return ALIAS[t]
    if target.startswith(("http://", "https://")):
        return target
    if "." in target and " " not in target:
        return f"https://{target}"
    raise ValueError(f"알 수 없는 별칭/URL: {target}\n등록된 별칭: {', '.join(sorted(ALIAS))}")


def _find_element_in_frames(page, finder_js: str, arg):
    """모든 프레임을 순회하며 finder_js로 매칭되는 element handle 반환. (frame, handle) 또는 (None, None)."""
    for frame in page.frames:
        try:
            handle = frame.evaluate_handle(finder_js, arg)
            # JS가 null을 반환하면 handle은 'null' jsHandle
            if handle.evaluate("e => e !== null"):
                return frame, handle
        except Exception:  # noqa: BLE001 - 여러 프레임(iframe 포함) 중 대상 요소를 찾는 read-only 헬퍼 — 프레임별 evaluate_handle 실패를 continue로 넘기고 못 찾으면 (None, None) 반환, 브라우저 조작 없는 탐색 유틸.
            continue
    return None, None


def _normalize_text(s: str) -> str:
    """공백/투명문자 정규화 — Smart Editor가 paste 텍스트를 NBSP 등으로 변환하는 케이스 대응."""
    if not s:
        return ""
    return (
        s.replace(" ", " ")  # NBSP
        .replace("​", "")  # zero-width space
        .replace("‌", "")  # ZWNJ
        .replace("‍", "")  # ZWJ
        .replace("\t", " ")
    )
