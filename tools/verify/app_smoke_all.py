"""여러 수동 점검(APP_VERIFY_c4/browser/server/apps.md)을 한 번에 돌리는 통합 스모크.

오늘 손으로 한 검증을 자동화 우선 원칙에 따라 한 명령으로 묶는다:
  1. 네이버 블로그 AI 일괄작성 dry-run (c4, APP_VERIFY_c4.md)
  2. 승인된 브라우저 지시 API dry-run (c4, APP_VERIFY_browser.md)
  3. 격리 서버 기동 + /health, 실제 WS 핸드셰이크(auth_ok) (W2, APP_VERIFY_server.md —
     핸드셰이크는 tools/verify/smoke_ws_handshake.py 를 그대로 호출)
  4. apps/ 독립 실행 앱 3종 기동 (W1, APP_VERIFY_apps.md)

모든 항목을 HAEHAN_DATA_DIR/임시 포트로 격리해서 돌리고, 실행 전후 운영 data/*.json·
~/.haehan_agent 의 md5 를 대조해 운영 상태를 안 건드렸는지 확인한다. 진짜 네트워크
필요한 항목(네이버 리서치 재수집 등)만 SKIP — "리서치 파일이 없는 신규설치 상태" 자체는
4dfa8267 의 폴백 경로를 실제로 타는지 보는 핵심 시험조건이라 SKIP 하지 않고 돌린다.

사용: python tools/verify/app_smoke_all.py [--json]
종료코드: 0 = FAIL 없음(SKIP 은 무방), 1 = FAIL 1개 이상.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file())
sys.path.insert(0, str(ROOT))
PY = sys.executable


def _run(
    cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 60
) -> subprocess.CompletedProcess:
    full_env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", **(env or {})}
    return subprocess.run(
        cmd, cwd=str(cwd or ROOT), env=full_env, capture_output=True, text=True, timeout=timeout, check=False
    )


def _md5(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.md5(path.read_bytes()).hexdigest()  # noqa: S324 - 무결성 확인용(보안 해시 아님)


def _fingerprint() -> dict[str, str | None]:
    """운영 data/*.json·~/.haehan_agent 의 md5 — 실행 전후 대조해 격리가 실제로 됐는지 확인."""
    out: dict[str, str | None] = {}
    data_dir = ROOT / "data"
    if data_dir.is_dir():
        for p in sorted(data_dir.glob("*.json")):
            out[f"data/{p.name}"] = _md5(p)
    home_cfg = Path.home() / ".haehan_agent" / "config.json"
    out["~/.haehan_agent/config.json"] = _md5(home_cfg)
    return out


def _result(name: str, status: str, detail: str = "") -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def check_naver_blog_dry_run() -> dict[str, str]:
    """APP_VERIFY_c4.md — blog_ai_batch_20.py --dry-run, 리서치 파일 없는 신규설치 상태(핵심 시험조건).

    4dfa8267(c4) 이전에는 리서치 파일이 없으면 dry-run 이 늘 "주제 선정 실패"로 끝났다
    (generate_topics() 의 dry-run 조기 return 이 get_topic_seed() 폴백에 전혀 안 닿음).
    그 결함을 고친 지금은 "파일 없음" 자체가 핵심 시험조건 — SKIP 이 아니라, 격리된 빈
    HAEHAN_DATA_DIR 로 돌려 폴백 경로가 실제로 주제를 ≥1개 만들어내는지가 PASS 기준이다.
    운영 data/ 는 전혀 건드리지 않음(임시폴더만 씀).
    """
    script = ROOT / "scripts" / "naver" / "blog" / "cli" / "blog_ai_batch_20.py"

    def _run_case(data_dir: str) -> tuple[int, str]:
        proc = _run(
            [PY, str(script), "--dry-run", "--count", "1"],
            env={"HAEHAN_NO_BROWSER_LAUNCH": "1", "HAEHAN_DATA_DIR": data_dir},
            timeout=120,
        )
        out = proc.stdout + proc.stderr
        return proc.returncode, out

    def _success_count(out: str) -> int:
        # "  성공: N/M" — 이미지 파일명에도 "[DRY]" 가 섞여 있어(image1.jpg 등) 그 토큰은
        # 못 쓴다(실측: count("[DRY]") 가 이미지 3장+요약 1줄로 4가 나와 틀림).
        m = re.search(r"성공:\s*(\d+)/\d+", out)
        return int(m.group(1)) if m else 0

    with tempfile.TemporaryDirectory(prefix="app_smoke_naver_empty_") as empty_dir:
        rc1, out1 = _run_case(empty_dir)
    n1 = _success_count(out1)
    ok1 = rc1 == 0 and "[DRY-RUN]" in out1 and "완료 요약" in out1 and n1 >= 1

    # 두 번째 케이스: 리서치 파일이 있을 때 "리서치 결과 직접 사용" 경로(폴백이 아닌 쪽)도
    # 깨지지 않았는지 — 최소 fixture(실제 스키마: generated_at·topics[].question_title/
    # keyword/question_description, get_researched_topics() 참고) 1건으로 확인.
    with tempfile.TemporaryDirectory(prefix="app_smoke_naver_fixture_") as fixture_dir:
        fixture = {
            "generated_at": datetime.datetime.now().isoformat(),
            "topics": [
                {
                    "question_title": "스모크 고정 주제 — 지식iN 질문 예시",
                    "keyword": "건설실무",
                    "question_description": "스모크 전용 최소 fixture",
                }
            ],
        }
        (Path(fixture_dir) / "blog_topic_research_latest.json").write_text(
            json.dumps(fixture, ensure_ascii=False), encoding="utf-8"
        )
        rc2, out2 = _run_case(fixture_dir)
    n2 = _success_count(out2)
    ok2 = rc2 == 0 and "리서치 매칭: 1개" in out2 and n2 >= 1

    if ok1 and ok2:
        return _result(
            "naver_blog_dry_run",
            "PASS",
            f"폴백경로(빈 데이터) 주제 {n1}건 + 리서치경로(fixture 1건) 주제 {n2}건 — 둘 다 생성",
        )
    detail = f"폴백케이스 ok={ok1}(exit={rc1}, 건수={n1}); 리서치케이스 ok={ok2}(exit={rc2}, 건수={n2})"
    return _result("naver_blog_dry_run", "FAIL", f"{detail}; tail={(out1 if not ok1 else out2)[-300:]!r}")


def check_browser_dry_run() -> dict[str, str]:
    """APP_VERIFY_browser.md — dry_run_approved_browser_instruction_api.py --json."""
    script = ROOT / "tools" / "verify" / "dry_run_approved_browser_instruction_api.py"
    proc = _run([PY, str(script), "--json"], timeout=60)
    out = proc.stdout.strip()
    if proc.returncode != 0:
        return _result("browser_dry_run", "FAIL", f"exit={proc.returncode} stderr={proc.stderr[-300:]!r}")
    try:
        payload = json.loads(out)
    except ValueError:
        return _result("browser_dry_run", "FAIL", f"JSON 파싱 실패: {out[:300]!r}")
    verdict = payload.get("verdict", "")
    if verdict == "PASS_APPROVED_BROWSER_INSTRUCTION_API_DRY_RUN_READY":
        return _result("browser_dry_run", "PASS", verdict)
    return _result("browser_dry_run", "FAIL", f"verdict={verdict}")


def check_isolated_server_health() -> dict[str, str]:
    """APP_VERIFY_server.md 중 health 부분만 — 격리 data/storage·임시 포트로 uvicorn 기동 후 /api/v1/health."""
    port = 18401
    with (
        tempfile.TemporaryDirectory(prefix="app_smoke_data_") as data_dir,
        tempfile.TemporaryDirectory(prefix="app_smoke_storage_") as storage_dir,
    ):
        env = {
            "HAEHAN_DATA_DIR": data_dir,
            "HAEHAN_STORAGE_DIR": storage_dir,
            "APP_PORT": str(port),
            "AUTH_ENABLED": "false",
        }
        proc = subprocess.Popen(
            [PY, "-m", "uvicorn", "ai_orchestrator.asgi:app", "--port", str(port)],
            cwd=str(ROOT),
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", **env},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            ok = False
            for _ in range(30):  # 최대 ~15초 기동 대기
                time.sleep(0.5)
                if proc.poll() is not None:
                    break
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=1) as resp:
                        if resp.status == 200 and json.loads(resp.read()).get("status") == "ok":
                            ok = True
                            break
                except (urllib.error.URLError, ConnectionError, OSError):
                    continue
            if ok:
                return _result("isolated_server_health", "PASS", f"port={port} /api/v1/health 200")
            return _result("isolated_server_health", "FAIL", "기동 시간 내 health 200 못 받음")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def check_ws_handshake() -> dict[str, str]:
    """APP_VERIFY_server.md 의 실제 WS 핸드셰이크(auth_ok) — 8ba71a67 로 HAEHAN_AGENT_WS_ONCE 를
    실제 구현한 뒤, tools/verify/smoke_ws_handshake.py(독립 스크립트, 빈 포트 자동선택+
    임시 config/agent_id+서버 기동→핸드셰이크→정리)로 옮겨졌다. 여기서는 그 run() 을 그대로
    호출만 한다(이름만 이 파일 컨벤션에 맞춰 _result 로 다시 감싸지 않고 그대로 반환).
    """
    from tools.verify.smoke_ws_handshake import run as _ws_handshake_run

    return _ws_handshake_run()


def check_standalone_apps() -> dict[str, str]:
    """APP_VERIFY_apps.md — marketing-standalone·ig-comment-dm-bot·youtube-analyzer-standalone."""
    results = []

    app = ROOT / "apps" / "marketing-standalone"
    proc = _run(
        [PY, "site_modules/blog_router.py", "draft.json", "--check", "--no-images"],
        cwd=app,
        timeout=30,
    )
    out = proc.stdout + proc.stderr
    results.append(
        "marketing-standalone:" + ("ok" if "라이선스가 등록되지 않았습니다" in out or proc.returncode == 0 else "fail")
    )

    app = ROOT / "apps" / "ig-comment-dm-bot"
    proc = _run(
        [PY, "-c", "import sys; sys.path.insert(0, '.'); import ui.main_window; print('IMPORT_OK')"],
        cwd=app,
        timeout=30,
    )
    results.append("ig-comment-dm-bot:" + ("ok" if "IMPORT_OK" in proc.stdout else "fail"))

    app = ROOT / "apps" / "youtube-analyzer-standalone"
    proc = _run([PY, "cli.py", "--help"], cwd=app, timeout=30)
    yt_ok = proc.returncode == 0 and "usage:" in (proc.stdout + proc.stderr).lower()
    if not yt_ok and "yt_dlp" in proc.stderr:
        results.append("youtube-analyzer-standalone:skip(yt-dlp 미설치 — 환경 사전조건)")
    else:
        results.append("youtube-analyzer-standalone:" + ("ok" if yt_ok else "fail"))

    failed = [r for r in results if ":fail" in r]
    if failed:
        return _result("standalone_apps", "FAIL", "; ".join(results))
    if any(":skip" in r for r in results):
        return _result("standalone_apps", "SKIP", "; ".join(results))
    return _result("standalone_apps", "PASS", "; ".join(results))


def main(argv: list[str] | None = None) -> int:
    as_json = "--json" in (argv or sys.argv[1:])

    before = _fingerprint()
    checks = [
        check_naver_blog_dry_run,
        check_browser_dry_run,
        check_isolated_server_health,
        check_ws_handshake,
        check_standalone_apps,
    ]
    results = []
    for check in checks:
        try:
            results.append(check())
        except Exception as exc:  # noqa: BLE001 - 한 항목의 예외가 나머지를 막지 않게
            results.append(_result(check.__name__, "FAIL", f"예외: {exc!r}"))
    after = _fingerprint()

    drift = {k: (before.get(k), after[k]) for k in after if before.get(k) != after[k]}
    results.append(
        _result(
            "operational_data_untouched",
            "FAIL" if drift else "PASS",
            json.dumps(drift, ensure_ascii=False) if drift else "md5 동일",
        )
    )

    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    summary = {"results": results, "fail_count": fail_count, "pass": fail_count == 0}

    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(f"[{r['status']}] {r['name']}: {r['detail']}")
        print(f"\n종합: {'PASS' if summary['pass'] else 'FAIL'} (FAIL {fail_count}건)")

    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
