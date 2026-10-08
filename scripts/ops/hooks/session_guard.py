"""세션 기록 크기 기반 새 세션 강제 훅. docs/specs/2026-09-24_session_handoff_guard.md

이벤트별 동작:
  UserPromptSubmit — 기록 크기(transcript_path)가 경고선/차단선 넘으면 안내·차단.
  SessionStart      — HANDOFF.md 요약을 맥락에 주입 + report-mode 정리.
  Stop / PreCompact — 조용히 handoff write (never block).

fail-open: 예상 못한 오류는 항상 exit 0 (차단 경로 제외).
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import session_handoff as sh  # type: ignore[import-not-found]  # 직접실행 시 스크립트 자기 폴더가 sys.path[0]


def _mb(path_str: str) -> float:
    try:
        p = Path(path_str)
        if not p.exists():
            return 0.0
        return p.stat().st_size / (1024 * 1024)
    except Exception:  # noqa: BLE001 - 세션 기록 크기 기반 handoff 강제 훅 - 파일명은 session_guard이나 로그아웃/보안 차단과 무관한 생산성 훅, 자체 문서화된 fail-open(exit 0)으로 세션을 죽이지 않기 위한 의도된 설계이며 실제 차단(exit 2) 경로는 이 except 밖에서 이미 처리됨
        return 0.0


def _handle_user_prompt_submit(payload: dict) -> int:
    cfg = sh.load_config()
    prompt = str(payload.get("prompt", "") or "")
    bypass = cfg.get("bypass_prefix", "!계속")
    if prompt.startswith(bypass):
        sh.log_event("bypass", prompt_head=prompt[:40])
        return 0

    transcript_path = payload.get("transcript_path", "") or ""
    size_mb = _mb(transcript_path)
    warn_mb = float(cfg.get("warn_mb", 8))
    block_mb = float(cfg.get("block_mb", 12))

    flag_path = sh._p(cfg.get("phase_done_flag", "data/impact/PHASE_DONE"))
    phase_done = flag_path.exists()

    if size_mb >= block_mb or phase_done:
        ok = sh.write()
        handoff_path = sh._p(cfg.get("handoff_path", "data/impact/HANDOFF.md"))
        if ok:
            msg = (
                f"세션 한도 도달({size_mb:.1f}MB) — 작업기록 저장 완료: {handoff_path}. "
                f"진행 중인 서브에이전트가 없으면 이 창에서 /clear 입력 후 '인계 이어서'라고 입력하세요. "
                f"(비상시 입력 앞에 {cfg.get('bypass_prefix', '!계속')})"
            )
            print(msg, file=sys.stderr)
            return 2
        else:
            print(
                f"[세션 경고] 인계 파일 저장 실패 — 차단하지 않고 계속 진행합니다. "
                f"현재 작업을 마무리하고 다시 저장을 시도하세요. (기록 {size_mb:.1f}MB)"
            )
            return 0

    if size_mb >= warn_mb:
        print(
            f"[세션 경고] 기록 {size_mb:.1f}MB — 진행 중 서브에이전트를 마무리(새 투입 금지)하고 "
            f"작업기록 저장 후 사용자에게 /clear 안내."
        )
        return 0

    return 0


def _handle_session_start(payload: dict) -> int:
    # source: "startup"(새 창) / "resume"(--resume) / "clear"(/clear 직후) — 모두 인계 요약 주입 대상.
    source = str(payload.get("source", "") or "")
    if source and source not in ("startup", "resume", "clear"):
        return 0
    try:
        cfg = sh.load_config()
        handoff_path = sh._p(cfg.get("handoff_path", "data/impact/HANDOFF.md"))
        if handoff_path.exists():
            age_days = (time.time() - handoff_path.stat().st_mtime) / 86400
            if age_days <= 7:
                sh.start(apply_cleanup=False)
    except Exception:  # noqa: BLE001 - 세션 기록 크기 기반 handoff 강제 훅 - 파일명은 session_guard이나 로그아웃/보안 차단과 무관한 생산성 훅, 자체 문서화된 fail-open(exit 0)으로 세션을 죽이지 않기 위한 의도된 설계이며 실제 차단(exit 2) 경로는 이 except 밖에서 이미 처리됨
        pass
    return 0


def _handle_quiet_write() -> int:
    # fail-open 훅 - handoff write 실패로 세션을 죽이지 않기 위한 의도된 설계(차단 경로는 이 함수 밖에서 별도 처리됨)
    with contextlib.suppress(Exception):
        sh.write()
    return 0


def main() -> int:
    # 훅 출력은 하네스가 UTF-8 로 읽는다. 파이프로 연결되면 파이썬 기본 인코딩이 cp949 라 한글이 깨져
    # 사용자에게 안내 문구(예: /clear 안내)가 읽히지 않았다(2026-10-01).
    for _stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001 - 세션 기록 크기 기반 handoff 강제 훅 - 파일명은 session_guard이나 로그아웃/보안 차단과 무관한 생산성 훅, 자체 문서화된 fail-open(exit 0)으로 세션을 죽이지 않기 위한 의도된 설계이며 실제 차단(exit 2) 경로는 이 except 밖에서 이미 처리됨
        payload = {}

    event = payload.get("hook_event_name", "")

    try:
        if event == "UserPromptSubmit":
            return _handle_user_prompt_submit(payload)
        if event == "SessionStart":
            return _handle_session_start(payload)
        if event in ("Stop", "PreCompact"):
            return _handle_quiet_write()
        return 0
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - 세션 기록 크기 기반 handoff 강제 훅 - 파일명은 session_guard이나 로그아웃/보안 차단과 무관한 생산성 훅, 자체 문서화된 fail-open(exit 0)으로 세션을 죽이지 않기 위한 의도된 설계이며 실제 차단(exit 2) 경로는 이 except 밖에서 이미 처리됨
        # fail-open — 훅이 세션을 절대 죽이면 안 된다 (차단 경로 제외 이미 위에서 처리됨)
        return 0


if __name__ == "__main__":
    sys.exit(main())
