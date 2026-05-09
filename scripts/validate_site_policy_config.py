"""site policy JSON config 검증 스크립트.

Usage:
    python scripts/validate_site_policy_config.py configs/site_policies/g2b.json
    python scripts/validate_site_policy_config.py configs/site_policies/  # 디렉터리 일괄 검증
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_FIELDS = (
    "site_id", "label", "allowed_hosts", "allowed_paths",
    "blocked_paths", "execution_location", "login_mode",
    "credential_policy", "capture_policy", "risk_level",
)

ALLOWED_EXECUTION_LOCATIONS = {"LOCAL_AGENT_REQUIRED"}
ALLOWED_LOGIN_MODES = {"PUBLIC_READONLY", "USER_LOGIN_REQUIRED"}
ALLOWED_CREDENTIAL_POLICIES = {"NO_CREDENTIAL_CAPTURE"}
ALLOWED_CAPTURE_POLICIES = {"NO_SCREENSHOT_NO_HAR"}
ALLOWED_RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}

FORBIDDEN_PATH_PATTERNS = ("login", "cert", "sign", "admin", "session", "cookie")


def _err(msg: str) -> dict:
    return {"ok": False, "error": msg}


def _ok(site_id: str, warnings: list[str]) -> dict:
    return {"ok": True, "site_id": site_id, "warnings": warnings}


def validate_config(data: dict) -> dict:
    warnings: list[str] = []

    for f in REQUIRED_FIELDS:
        if f not in data:
            return _err(f"필수 필드 누락: {f}")

    if not isinstance(data["allowed_hosts"], list) or not data["allowed_hosts"]:
        return _err("allowed_hosts는 비어있지 않은 배열이어야 합니다")

    if data["execution_location"] not in ALLOWED_EXECUTION_LOCATIONS:
        return _err(f"execution_location 허용값: {ALLOWED_EXECUTION_LOCATIONS}")

    if data["login_mode"] not in ALLOWED_LOGIN_MODES:
        return _err(f"login_mode 허용값: {ALLOWED_LOGIN_MODES}")

    if data["credential_policy"] not in ALLOWED_CREDENTIAL_POLICIES:
        return _err(f"credential_policy 허용값: {ALLOWED_CREDENTIAL_POLICIES}")

    if data["capture_policy"] not in ALLOWED_CAPTURE_POLICIES:
        return _err(f"capture_policy 허용값: {ALLOWED_CAPTURE_POLICIES}")

    if data["risk_level"] not in ALLOWED_RISK_LEVELS:
        return _err(f"risk_level 허용값: {ALLOWED_RISK_LEVELS}")

    # allowed_paths에 위험 패턴 포함 경고
    for path in data.get("allowed_paths", []):
        for pat in FORBIDDEN_PATH_PATTERNS:
            if pat in path.lower():
                warnings.append(f"allowed_paths에 위험 패턴 포함: {path!r} (패턴: {pat})")

    # blocked_paths에 위험 경로 누락 경고
    blocked = [p.lower() for p in data.get("blocked_paths", [])]
    if not any("login" in b or "cert" in b or "admin" in b for b in blocked):
        warnings.append("blocked_paths에 login/cert/admin 경로가 없습니다 — 의도적인 경우 notes에 명시 권장")

    return _ok(data["site_id"], warnings)


def validate_file(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return _err(f"JSON 파싱 오류: {e}")
    result = validate_config(data)
    result["file"] = str(path)
    return result


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python scripts/validate_site_policy_config.py <json파일 또는 디렉터리>")
        sys.exit(1)

    target = Path(sys.argv[1])
    files: list[Path] = []

    if target.is_dir():
        files = sorted(target.glob("*.json"))
        if not files:
            print(f"[WARN] {target}에 JSON 파일 없음")
            sys.exit(0)
    elif target.is_file():
        files = [target]
    else:
        print(f"[ERROR] 존재하지 않는 경로: {target}")
        sys.exit(1)

    all_ok = True
    for f in files:
        result = validate_file(f)
        if result["ok"]:
            warns = result.get("warnings", [])
            status = "✅ PASS" if not warns else "⚠️  PASS(경고)"
            print(f"{status}  {result['file']}  site_id={result['site_id']}")
            for w in warns:
                print(f"       경고: {w}")
        else:
            print(f"❌ FAIL  {result['file']}  오류: {result['error']}")
            all_ok = False

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
