"""여러 수동 점검(APP_VERIFY_c4/browser/server/apps.md)을 한 번에 돌리는 통합 스모크.

오늘 손으로 한 검증을 자동화 우선 원칙에 따라 한 명령으로 묶는다:
  1. 네이버 블로그 AI 일괄작성 dry-run (c4, APP_VERIFY_c4.md)
  2. 승인된 브라우저 지시 API dry-run (c4, APP_VERIFY_browser.md)
  3. 격리 서버 기동 + /health (W2, APP_VERIFY_server.md — 여기선 health 만. WS 핸드셰이크는
     HAEHAN_AGENT_WS_ONCE 미구현 결함 때문에 자리만 두고 SKIP, W2 수정 후 채운다)
  4. apps/ 독립 실행 앱 3종 기동 (W1, APP_VERIFY_apps.md)

모든 항목을 HAEHAN_DATA_DIR/임시 포트로 격리해서 돌리고, 실행 전후 운영 data/*.json·
~/.haehan_agent 의 md5 를 대조해 운영 상태를 안 건드렸는지 확인한다. 네트워크·사전조건
(신선한 리서치 데이터 등) 이 없는 항목은 SKIP 으로 표시(실패로 보지 않음).

사용: python tools/verify/app_smoke_all.py [--json]
종료코드: 0 = FAIL 없음(SKIP 은 무방), 1 = FAIL 1개 이상.
"""

from __future__ import annotations

import hashlib
import json
import os
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
    """APP_VERIFY_c4.md — blog_ai_batch_20.py --dry-run. 리서치 데이터가 없거나 오래되면 SKIP.

    c4 의 조사(APP_VERIFY_c4.md)에 따르면 리서치 30일초과/누락 시 '주제 선정 실패'로 그냥
    멈추는 게 의도된 안전장치(F2) — 그 상태를 FAIL 로 보지 않고, 자동화 스모크는 사전조건
    (신선한 리서치 파일) 이 있을 때만 실제로 돌리고 없으면 SKIP 한다(운영 파일을 건드리거나
    타임스탬프를 조작해 억지로 통과시키지 않음 — 그건 사람이 c4 방식대로 격리 복사본에서
    하는 일이지 범용 자동 스모크가 할 일이 아니다).
    """
    research = ROOT / "data" / "blog_topic_research_latest.json"
    if not research.is_file():
        return _result(
            "naver_blog_dry_run", "SKIP", "data/blog_topic_research_latest.json 없음 — 네트워크로 재생성 필요"
        )
    try:
        payload = json.loads(research.read_text(encoding="utf-8"))
        generated_at = payload.get("generated_at", "")
        age_days = (
            (time.time() - time.mktime(time.strptime(generated_at[:10], "%Y-%m-%d"))) / 86400 if generated_at else 999
        )
    except ValueError, OSError:
        age_days = 999
    if age_days > 30:
        return _result(
            "naver_blog_dry_run", "SKIP", f"리서치 데이터 {age_days:.0f}일 경과(30일 제한) — 네트워크로 재생성 필요"
        )

    script = ROOT / "scripts" / "naver" / "blog" / "cli" / "blog_ai_batch_20.py"
    proc = _run([PY, str(script), "--dry-run", "--count", "1"], env={"HAEHAN_NO_BROWSER_LAUNCH": "1"}, timeout=120)
    out = proc.stdout + proc.stderr
    if proc.returncode == 0 and "[DRY-RUN]" in out and "완료 요약" in out:
        return _result("naver_blog_dry_run", "PASS", "DRY-RUN 완료 요약 확인")
    return _result("naver_blog_dry_run", "FAIL", f"exit={proc.returncode} tail={out[-300:]!r}")


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
                except urllib.error.URLError, ConnectionError, OSError:
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
    """APP_VERIFY_server.md 의 실제 WS 핸드셰이크(auth_ok) — HAEHAN_AGENT_WS_ONCE 가 아직
    구현 안 돼 있어(agent.py 가 값을 setdefault 만 하고 읽는 코드가 없음, W2 발견) 자동
    스모크에서 돌리면 --once 로 끝내지 못하고 멈춘다. W2 가 websocket_client.py 의 수신
    루프에 그 체크를 넣은 뒤 이 자리를 채운다 — 지금은 자리만 두고 SKIP.
    """
    return _result("ws_handshake", "SKIP", "HAEHAN_AGENT_WS_ONCE 미구현(W2 수정 대기) — 자리만 둠")


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
