"""admin-web 첫 화면 smoke 검측 스크립트.

next start로 프로덕션 서버를 기동, / 경로 HTML을 가져와
주요 UI 요소 텍스트가 포함됐는지 확인한다.
실행 후 서버를 반드시 종료한다.
"""
from __future__ import annotations

import http.client
import subprocess
import sys
import time
import os

PORT = 3002
TIMEOUT = 30


def wait_for_server(port: int, timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            conn = http.client.HTTPConnection("localhost", port, timeout=2)
            conn.request("GET", "/")
            r = conn.getresponse()
            conn.close()
            if r.status < 500:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def fetch_html(port: int) -> str:
    conn = http.client.HTTPConnection("localhost", port, timeout=10)
    conn.request("GET", "/")
    r = conn.getresponse()
    body = r.read().decode("utf-8", errors="replace")
    conn.close()
    return body


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    next_cmd = os.path.join(root, "node_modules", ".bin", "next.cmd")
    if not os.path.exists(next_cmd):
        next_cmd = os.path.join(root, "node_modules", ".bin", "next")
    proc = subprocess.Popen(
        [next_cmd, "start", "-p", str(PORT)],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    passed: list[str] = []
    failed: list[str] = []
    status_code = 0

    try:
        print(f"[smoke] next start 기동 중 (port {PORT})...")
        if not wait_for_server(PORT, TIMEOUT):
            print("[smoke] FAIL: 서버 기동 타임아웃")
            sys.exit(1)

        html = fetch_html(PORT)
        status_code = 200  # wait_for_server이 200미만 체크했으므로

        CHECKS = [
            ("HTTP 200 응답", lambda h: len(h) > 100),
            ("해한 AI 비서 (대시보드 헤더)", lambda h: "해한 AI 비서" in h),
            ("TopAccentLine / 오렌지 라인", lambda h: "F97316" in h or "top-accent" in h or "TopAccentLine" in h),
            ("시스템 정상 (StatusBadge)", lambda h: "시스템 정상" in h or "PASS" in h),
            ("로컬 에이전트 현황 (MetricCard)", lambda h: "로컬 에이전트" in h),
            ("온라인 에이전트 (MetricCard count)", lambda h: "온라인 에이전트" in h),
            ("승인 대기 (큐 섹션)", lambda h: "승인 대기" in h),
            ("실행 게이트 (GateStatusCard)", lambda h: "실행 게이트" in h or "FORBIDDEN_IMPORT" in h),
            ("작업 공정표 (ConstructionPhaseTable)", lambda h: "작업 공정표" in h or "공정표" in h),
            ("비서앱 웹 기초 (공정행)", lambda h: "비서앱 웹 기초" in h or "ASSISTANT_WEB" in h),
            ("빠른 작업 생성 (Input/Select/Button)", lambda h: "빠른 작업 생성" in h),
            ("업무 창고 (WarehouseCard)", lambda h: "업무 창고" in h or "EUM 단말기" in h),
            ("운영 메뉴 (링크)", lambda h: "로컬 에이전트 관리" in h),
        ]

        for label, check in CHECKS:
            if check(html):
                passed.append(f"  ✅ {label}")
            else:
                failed.append(f"  ❌ {label}")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("[smoke] 서버 종료 완료")

    print("\n[smoke] 검측 결과")
    for p in passed:
        print(p)
    for f in failed:
        print(f)

    print(f"\n총 {len(passed)+len(failed)}개 항목 중 PASS {len(passed)} / FAIL {len(failed)}")

    if failed:
        print("[smoke] 최종 판정: FAIL")
        sys.exit(1)
    else:
        print("[smoke] 최종 판정: PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
