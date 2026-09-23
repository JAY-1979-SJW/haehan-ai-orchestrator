"""PYINSTALLER_BUILD_EXEC_V2_01 audit — GUI 포함 재빌드 검증."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

DIST_DIR = Path("dist/HaehanAI-Agent")
EXE = DIST_DIR / "HaehanAI-Agent.exe"
BUILD_REPORT = Path("data/inspection/local_agent_installer_package/build_report.json")
OUT_DIR = Path("data/inspection/local_agent_gui_build_exec_v2")


@dataclass
class GuiBuildVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


_TOKEN_LEAK_PATTERNS = (
    re.compile(r'"device_token"\s*:\s*"[A-Za-z0-9._\-]{8,}"'),
    re.compile(r'"registration_code"\s*:\s*"[A-Za-z0-9._\-]{8,}"'),
)


def _has_leak(text: str) -> list[str]:
    return [p.pattern for p in _TOKEN_LEAK_PATTERNS if p.search(text or "")]


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def _run_exe(args, timeout=30):
    if not EXE.exists():
        return {"rc": -1, "out": "", "err": "exe missing"}
    try:
        r = subprocess.run([str(EXE), *args], capture_output=True, text=True, timeout=timeout, errors="replace")
        return {"rc": r.returncode, "out": r.stdout, "err": r.stderr}
    except subprocess.TimeoutExpired:
        return {"rc": -1, "out": "", "err": "timeout"}
    except Exception as exc:
        return {"rc": -1, "out": "", "err": str(exc)[:200]}


def _gui_launch_smoke(timeout: float = 5.0) -> dict:
    """exe --gui 를 백그라운드로 띄워 timeout 내 안 죽으면 PASS."""
    if not EXE.exists():
        return {"ok": False, "reason": "exe missing"}
    try:
        p = subprocess.Popen(
            [str(EXE), "--gui"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except Exception as exc:
        return {"ok": False, "reason": f"launch_error:{exc}"}
    t0 = time.time()
    while time.time() - t0 < timeout:
        if p.poll() is not None:
            try:
                p.stdout.read().decode("utf-8", errors="replace")
                err = p.stderr.read().decode("utf-8", errors="replace")
            except Exception:
                _out, err = "", ""
            return {"ok": False, "reason": "exited_early", "rc": p.returncode, "stderr_tail": (err or "")[-300:]}
        time.sleep(0.5)
    # 살아있음 — kill
    try:
        p.terminate()
        try:
            p.wait(timeout=3)
        except Exception:
            p.kill()
    except Exception:
        pass
    return {"ok": True, "alive_seconds": timeout}


def judge_gui_build(*, gui_smoke_ok: bool | None = None, cli_regression_ok: bool = True) -> GuiBuildVerdict:
    metrics = {
        "exe_exists": EXE.exists(),
        "build_report_exists": BUILD_REPORT.exists(),
    }

    # FAIL_DIST_MISSING
    if not EXE.exists():
        return GuiBuildVerdict(False, "FAIL_DIST_MISSING", reasons=[f"exe not found: {EXE}"], metrics=metrics)

    # FAIL_BUILD_FAILED — build_report ok=False
    if BUILD_REPORT.exists():
        br = json.loads(BUILD_REPORT.read_text(encoding="utf-8"))
        metrics["build_ok"] = br.get("ok", False)
        metrics["pyinstaller_version"] = br.get("pyinstaller_version", "")
        if not br.get("ok"):
            return GuiBuildVerdict(False, "FAIL_BUILD_FAILED", reasons=["build_report.ok=False"], metrics=metrics)
        # hidden imports — build_report 의 cmd 에 포함됐는지
        cmd = br.get("cmd", "")
        for imp in ("tkinter", "pystray", "PIL"):
            if imp not in cmd:
                return GuiBuildVerdict(
                    False, "FAIL_BUILD_FAILED", reasons=[f"hidden import missing in build cmd: {imp}"], metrics=metrics
                )

    metrics["exe_size_bytes"] = EXE.stat().st_size
    metrics["exe_sha256"] = _sha256(EXE)

    # FAIL_CLI_REGRESSION — self-test
    st = _run_exe(["--self-test"], timeout=30)
    metrics["self_test_rc"] = st["rc"]
    if st["rc"] != 0:
        return GuiBuildVerdict(False, "FAIL_CLI_REGRESSION", reasons=[f"self-test rc={st['rc']}"], metrics=metrics)
    try:
        sjson = json.loads(st["out"])
        if not sjson.get("ok"):
            return GuiBuildVerdict(False, "FAIL_CLI_REGRESSION", reasons=["self-test ok=False"], metrics=metrics)
    except Exception:
        return GuiBuildVerdict(False, "FAIL_CLI_REGRESSION", reasons=["self-test json parse failed"], metrics=metrics)

    # diagnostics
    dg = _run_exe(["--diagnostics"], timeout=15)
    metrics["diagnostics_rc"] = dg["rc"]
    if dg["rc"] != 0:
        return GuiBuildVerdict(False, "FAIL_CLI_REGRESSION", reasons=[f"diagnostics rc={dg['rc']}"], metrics=metrics)

    # FAIL_TOKEN_LEAK — self-test/diagnostics 출력
    for name, txt in (
        ("self_test_out", st["out"]),
        ("self_test_err", st["err"]),
        ("diagnostics_out", dg["out"]),
        ("diagnostics_err", dg["err"]),
    ):
        leaks = _has_leak(txt)
        if leaks:
            return GuiBuildVerdict(False, "FAIL_TOKEN_LEAK", reasons=[f"{name}:{leaks[:2]}"], metrics=metrics)

    # FAIL_CLI_REGRESSION (외부 신호)
    if not cli_regression_ok:
        return GuiBuildVerdict(
            False, "FAIL_CLI_REGRESSION", reasons=["external signal: cli tests failed"], metrics=metrics
        )

    # FAIL_GUI_ENTRYPOINT_BROKEN / FAIL_GUI_WINDOW_NOT_CREATED
    if gui_smoke_ok is None:
        # 본 audit 단독 실행 시: smoke 자동 실행
        smoke = _gui_launch_smoke(timeout=5.0)
        metrics["gui_smoke"] = smoke
        if not smoke.get("ok"):
            return GuiBuildVerdict(
                False, "FAIL_GUI_WINDOW_NOT_CREATED", reasons=[f"gui smoke: {smoke}"], metrics=metrics
            )
    elif gui_smoke_ok is False:
        return GuiBuildVerdict(
            False, "FAIL_GUI_WINDOW_NOT_CREATED", reasons=["external signal: GUI did not start"], metrics=metrics
        )
    else:
        metrics["gui_smoke"] = {"ok": True, "external_signal": True}

    # WARN
    onefile_exe = Path("dist/HaehanAI-Agent.exe")
    metrics["onefile_built"] = onefile_exe.exists()
    return GuiBuildVerdict(
        False, "WARN_UNSIGNED_BINARY", reasons=["dist built but unsigned (code signing OUT_OF_SCOPE)"], metrics=metrics
    )


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--gui-smoke-skip", action="store_true", help="GUI launch smoke 생략 (headless 환경)")
    args = ap.parse_args(argv)
    v = judge_gui_build(
        gui_smoke_ok=True if args.gui_smoke_skip else None,
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "audit_result.json").write_text(
        json.dumps(
            {"verdict": v.code, "passed": v.passed, "reasons": v.reasons, "metrics": v.metrics},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "verdict": v.code,
                "passed": v.passed,
                "reasons": v.reasons,
                "metrics": {k: vv for k, vv in v.metrics.items() if k != "self_test"},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if v.passed else 1


if __name__ == "__main__":
    sys.exit(main())
