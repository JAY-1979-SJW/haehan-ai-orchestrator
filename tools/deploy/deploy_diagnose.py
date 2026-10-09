"""deploy_diagnose.py — 서버 배포 반영 진단 (원격 안전 점검).

로컬/CI 어디서나 실행. 컨테이너 CLI 직접 호출 없음 — 호스트 명령은
docs/deploy_troubleshooting.md 참고. push 후 새 코드가 프로덕션에 반영됐는지
원격 엔드포인트로 판별한다.

    python tools/deploy/deploy_diagnose.py
"""

from __future__ import annotations

import subprocess
import urllib.error
import urllib.request

PROD = "https://haehan-ai.kr/orchestrator/api/v1"
# 신규 배포 여부 판별용 라우트 (구 이미지엔 없음)
PROBE_ROUTES = ["/health", "/grant-radar/report"]


def _curl(url: str) -> tuple[int | None, str]:
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.read(80).decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001 - HTTP 상태조회/git 명령 실행 실패를 오류 문자열로 반환하는 읽기전용 배포 진단 도구 — 쓰기 없음
        return None, str(e)[:60]


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, encoding="utf-8", timeout=20
        ).stdout.strip()
    except Exception as e:  # noqa: BLE001 - HTTP 상태조회/git 명령 실행 실패를 오류 문자열로 반환하는 읽기전용 배포 진단 도구 — 쓰기 없음
        return f"err:{e}"


def main() -> int:
    print("=== 서버 배포 진단 ===\n")

    print("[1] 로컬/origin 동기화")
    print("  로컬 HEAD     :", _git("log", "-1", "--oneline"))
    _git("fetch", "origin", "-q")
    ahead = _git("log", "--oneline", "origin/master..HEAD")
    print("  origin 미푸시 :", ahead or "(없음 — origin 동기화됨)")
    print()

    print("[2] 프로덕션 엔드포인트")
    codes = {}
    for r in PROBE_ROUTES:
        code, body = _curl(PROD + r)
        codes[r] = code
        print(f"  {r:28} → {code} {body[:40]}")
    print()

    print("[3] 판정")
    if codes.get("/health") == 200 and codes.get("/grant-radar/report") in (404, None):
        print("  ⚠️ 서버가 구 이미지 실행 중 (배포 미반영).")
        print("     push·webhook은 정상이어도 호스트 재빌드 단계가 실패/미완료일 수 있음.")
        print("     → 호스트에서 점검 (docs/deploy_troubleshooting.md):")
        print("       1) 서버 레포 최신 커밋 반영 여부")
        print("       2) 컨테이너 재빌드/재기동 상태·로그")
        print("       3) 배포 트리거 데몬 동작 여부")
    elif codes.get("/grant-radar/report") == 200:
        print("  ✅ 신규 코드 반영됨 (grant-radar 라우트 응답).")
    else:
        print("  ❓ health 비정상 — 서버/프록시 상태 먼저 확인.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
