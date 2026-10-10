"""navigator_blog — Naver 블로그 글 자동 작성 워크플로우."""

from __future__ import annotations

import subprocess
import sys
import time

from scripts.browser.navigator.navigator_common import ROOT
from scripts.common.logger import get_logger
from scripts.common.op_log import log_op

_log = get_logger(__name__)


def write_blog_post(
    title: str,
    body: str,
    image_path: str | None = None,
    save_draft: bool = True,
) -> bool:
    """Naver 블로그 글 1편 자동 작성 (제목 + 본문 + 선택 이미지 + 임시저장).

    각 단계를 별도 subprocess로 cdp_client CLI(cli.py) 명령 실행 — Playwright sync 중첩 회피.
    발행은 절대 자동 안 함. 임시저장까지만 수행.
    """
    print("=" * 60)
    print("블로그 글 작성 시작")
    print(f"  제목: {title!r}  본문: {body[:40]!r}  이미지: {image_path or '없음'}  임시저장: {save_draft}")
    print("=" * 60)
    _log.info("write_blog_post: title=%s image=%s", title[:40], image_path)
    _t_blog = time.perf_counter()

    script = str(ROOT / "scripts" / "browser" / "cdp" / "cli.py")
    py = sys.executable

    def _run(args: list[str], label: str, soft: bool = False) -> bool:
        print(f"\n--- {label} ---")
        r = subprocess.run([py, script] + args, cwd=str(ROOT))
        ok = r.returncode == 0
        if soft and not ok:
            print(f"--- {label} (스킵, 해당 없음) ---")
        else:
            print(f"--- {label} {'✓' if ok else '✗'} (exit={r.returncode}) ---")
        return ok

    # 1. 글쓰기 페이지 진입 (현재 URL 무관 — goto는 idempotent)
    _run(["goto", "https://blog.naver.com/skyjwsin?Redirect=Write"], "글쓰기 페이지 이동")
    time.sleep(2)

    # 1.5. 헬스 프로브 — Smart Editor 로드 완료까지 대기
    if not _run(
        ["is-ready", "url_contains:blog.naver", "readystate", "has_element:.se-text-paragraph", "has_button:저장"],
        "에디터 준비 헬스 체크",
    ):
        print("\n⛔ 에디터 로드 안 됨 — 후속 단계 중단")
        return False

    # 2. 임시저장 복원 모달 처리 — 전용 핸들러 (탐지 + 취소 클릭, 없으면 스킵)
    _run(["handle-draft-popup"], "복원 팝업 처리", soft=True)
    time.sleep(0.5)

    # 3. 제목 + 즉시 검증
    ok_t = _run(["type-into", "title", title], "제목 입력")
    time.sleep(0.5)
    ok_t_v = _run(["verify-input", title[:15]], "제목 즉시 검증") if ok_t else False
    if not (ok_t and ok_t_v):
        print("\n⛔ 제목 입력/검증 실패 → 후속 단계 중단 (본문/이미지/저장 실행 안 함)")
        print("=" * 60)
        return False

    # 4. 본문 + 즉시 검증
    ok_b = _run(["type-into", "body", body], "본문 입력")
    time.sleep(0.5)
    ok_b_v = _run(["verify-input", body[:15]], "본문 즉시 검증") if ok_b else False
    if not (ok_b and ok_b_v):
        print("\n⛔ 본문 입력/검증 실패 → 이미지/저장 중단")
        print("=" * 60)
        return False

    # 5. 이미지 paste
    if image_path:
        _run(["paste-image", image_path, "body"], "이미지 paste")
        time.sleep(1)

    # 6. 임시저장
    if save_draft:
        _run(["click-button", "저장"], "임시저장")
        time.sleep(1)

    elapsed_blog = int((time.perf_counter() - _t_blog) * 1000)
    print("\n" + "=" * 60)
    print("✓ 블로그 글 작성 흐름 완료")
    print("=" * 60)
    log_op("write_blog_post", ok=True, duration_ms=elapsed_blog, title=title[:60], has_image=image_path is not None)
    return True
