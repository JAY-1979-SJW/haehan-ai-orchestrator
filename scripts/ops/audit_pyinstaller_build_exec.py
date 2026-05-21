"""PYINSTALLER_BUILD_EXEC_01 audit — 실 PyInstaller 빌드 + exe smoke 검증."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BuildExecVerdict:
    passed: bool
    code: str
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


DIST_DIR = Path("dist/HaehanAI-Agent")
EXE = DIST_DIR / "HaehanAI-Agent.exe"
BUILD_REPORT = Path("data/inspection/local_agent_installer_package/build_report.json")


_FORBIDDEN_PATTERNS = (
    re.compile(r'"device_token"\s*:\s*"[A-Za-z0-9._\-]{8,}"'),
    re.compile(r'"registration_code"\s*:\s*"[A-Za-z0-9._\-]{8,}"'),
    re.compile(r"Authorization\s*:\s*Bearer", re.IGNORECASE),
)


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_exe(args: list[str], timeout: float = 20.0) -> dict:
    if not EXE.exists():
        return {"rc": -1, "out": "", "err": "exe missing"}
    try:
        r = subprocess.run([str(EXE), *args], capture_output=True,
                           text=True, timeout=timeout, errors="replace")
        return {"rc": r.returncode, "out": r.stdout, "err": r.stderr}
    except Exception as exc:
        return {"rc": -1, "out": "", "err": str(exc)[:200]}


def _has_token_leak(text: str) -> list[str]:
    hits = []
    for pat in _FORBIDDEN_PATTERNS:
        if pat.search(text or ""):
            hits.append(pat.pattern)
    return hits


def judge_build_exec(*, run_live_smoke: bool = False) -> BuildExecVerdict:
    metrics = {
        "exe_exists": EXE.exists(),
        "build_report_exists": BUILD_REPORT.exists(),
    }

    # FAIL_PYINSTALLER_MISSING
    try:
        r = subprocess.run([sys.executable, "-m", "PyInstaller", "--version"],
                           capture_output=True, text=True, timeout=10)
        ver = r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        ver = ""
    metrics["pyinstaller_version"] = ver
    if not ver:
        return BuildExecVerdict(False, "FAIL_PYINSTALLER_MISSING",
                                reasons=["pyinstaller not available"],
                                metrics=metrics)

    # FAIL_DIST_MISSING
    if not EXE.exists():
        return BuildExecVerdict(False, "FAIL_DIST_MISSING",
                                reasons=[f"exe not found: {EXE}"],
                                metrics=metrics)

    # FAIL_BUILD_FAILED — build_report 에 ok=False
    if BUILD_REPORT.exists():
        br = json.loads(_read(BUILD_REPORT))
        metrics["build_report_ok"] = br.get("ok", False)
        metrics["build_report_mode"] = br.get("mode", "")
        if br.get("ok") is False:
            return BuildExecVerdict(False, "FAIL_BUILD_FAILED",
                                    reasons=[f"build_report.ok=False: {br.get('error','')[:200]}"],
                                    metrics=metrics)

    # exe size + sha256
    metrics["exe_size_bytes"] = EXE.stat().st_size
    metrics["exe_sha256"] = _sha256(EXE)

    # FAIL_EXE_SELF_TEST_FAILED
    st = _run_exe(["--self-test"], timeout=30)
    metrics["self_test_rc"] = st["rc"]
    if st["rc"] != 0:
        return BuildExecVerdict(False, "FAIL_EXE_SELF_TEST_FAILED",
                                reasons=[f"rc={st['rc']} err={(st['err'] or '')[:200]}"],
                                metrics=metrics)
    # self-test JSON parse
    try:
        st_json = json.loads(st["out"])
        metrics["self_test_ok"] = st_json.get("ok", False)
        if not st_json.get("ok"):
            return BuildExecVerdict(False, "FAIL_EXE_SELF_TEST_FAILED",
                                    reasons=[f"self_test.ok=False: {st_json.get('checks',{})}"],
                                    metrics=metrics)
        if st_json["checks"].get("diagnostics_render_leaks", []) != []:
            return BuildExecVerdict(False, "FAIL_TOKEN_LEAK",
                                    reasons=["diagnostics render leaks tokens"],
                                    metrics=metrics)
        if "available=True" not in st_json["checks"].get("token_store_backend", ""):
            return BuildExecVerdict(False, "FAIL_CONFIG_STORE_BROKEN",
                                    reasons=[f"token_store backend not available"],
                                    metrics=metrics)
    except Exception as exc:
        return BuildExecVerdict(False, "FAIL_EXE_SELF_TEST_FAILED",
                                reasons=[f"self_test output parse: {exc}"],
                                metrics=metrics)

    # FAIL_DIAGNOSTICS_FAILED
    dg = _run_exe(["--diagnostics"], timeout=15)
    metrics["diagnostics_rc"] = dg["rc"]
    if dg["rc"] != 0:
        return BuildExecVerdict(False, "FAIL_DIAGNOSTICS_FAILED",
                                reasons=[f"rc={dg['rc']}"], metrics=metrics)

    # FAIL_TOKEN_LEAK — self-test/diagnostics output 에 raw token 패턴
    leaks = (_has_token_leak(st["out"]) + _has_token_leak(st["err"])
             + _has_token_leak(dg["out"]) + _has_token_leak(dg["err"]))
    if leaks:
        return BuildExecVerdict(False, "FAIL_TOKEN_LEAK",
                                reasons=[f"raw token pattern in output: {leaks[:3]}"],
                                metrics=metrics)

    # build_report 에 raw token 누설?
    if BUILD_REPORT.exists():
        rl = _has_token_leak(_read(BUILD_REPORT))
        if rl:
            return BuildExecVerdict(False, "FAIL_TOKEN_LEAK",
                                    reasons=[f"raw token in build_report: {rl}"],
                                    metrics=metrics)

    # WARN_ONEFILE_NOT_BUILT — onefile 산출 부재
    onefile_exe = Path("dist/HaehanAI-Agent.exe")
    metrics["onefile_built"] = onefile_exe.exists()
    if not onefile_exe.exists():
        # 라이브 register 까지 OK 면 PASS 전에 WARN 메시지로
        if not run_live_smoke:
            return BuildExecVerdict(False, "WARN_LIVE_REGISTER_NOT_TESTED",
                                    reasons=["onefile not built and live register not run"],
                                    metrics=metrics)

    # WARN_UNSIGNED_BINARY (코드 서명 OUT_OF_SCOPE)
    return BuildExecVerdict(False, "WARN_UNSIGNED_BINARY",
                            reasons=["dist built but unsigned (code signing OUT_OF_SCOPE)"],
                            metrics=metrics)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-smoke", action="store_true")
    args = ap.parse_args(argv)
    v = judge_build_exec(run_live_smoke=args.live_smoke)
    print(json.dumps({"verdict": v.code, "passed": v.passed,
                      "reasons": v.reasons, "metrics": v.metrics},
                     ensure_ascii=False, indent=2))
    return 0 if v.passed else 1


if __name__ == "__main__":
    sys.exit(main())
