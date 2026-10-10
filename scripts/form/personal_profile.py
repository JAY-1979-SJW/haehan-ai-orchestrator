"""회원가입/폼 채우기용 개인정보 프로필 — Fernet 암호화 저장.

저장 위치: data/profile.json (암호화 필드)
키 재사용: scripts.auth.credentials._get_or_create_key (data/.cred.key)

저장 필드 (예시):
    name, name_en, email, phone, birth (YYYY-MM-DD),
    gender ("M"|"F"), zipcode, address, address_detail,
    default_id, default_pw

사이트별 오버라이드:
    profile.override(site_key)  → 사이트 전용 ID/PW 등
    저장 위치: data/profile.json 의 "_overrides" 키 아래

민감 필드는 모두 암호화. 비민감(이메일/이름)은 평문도 허용 (가독성).
실제 구현은 모든 값을 일관되게 암호화.

사용:
    from scripts.form.personal_profile import get_value, set_profile, get_profile
    set_profile(name="홍길동", email="...", ...)
    val = get_value("name")             # "홍길동"
    val = get_value("default_id", site="naver")  # 사이트별 우선
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

from cryptography.fernet import InvalidToken

from ai_orchestrator.paths.runtime import atomic_write_text, data_dir

ROOT = Path(__file__).resolve().parents[2]
PROFILE_FILE = data_dir() / "profile.json"

# 공통 필드 카탈로그 — 회원가입에서 자주 쓰이는 역할
KNOWN_FIELDS = [
    "name",
    "name_en",
    "name_first",
    "name_last",
    "email",
    "phone",
    "birth",
    "birth_year",
    "birth_month",
    "birth_day",
    "gender",
    "zipcode",
    "address",
    "address_detail",
    "default_id",
    "default_pw",
]


def _crypto():
    """credentials.py 의 키를 그대로 재사용."""
    from scripts.auth.credentials import _fernet

    return _fernet()


def _encrypt(v: str) -> str:
    if not v:
        return ""
    return _crypto().encrypt(v.encode("utf-8")).decode("ascii")


def _decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _crypto().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""


def _load_raw() -> dict:
    if not PROFILE_FILE.exists():
        return {}
    try:
        return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 폼 자동입력용 개인정보 프로필 저장소(Fernet 암호화 저장) -- JSON 파싱 실패 시 빈 딕셔너리 반환(암호화된 파일 형식 오류일 뿐, 복호화 실패는 InvalidToken으로 별도 처리되어 평문 노출 없음)
        return {}


def _save_raw(data: dict) -> None:
    PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(PROFILE_FILE, json.dumps(data, ensure_ascii=False, indent=2))
    # 저장 파일 권한(chmod 600) 설정 실패는 무시 -- 파일 저장 자체는 이미 완료된 뒤의 부가적 권한 강화 조치이며 Windows 등 chmod 미지원 환경에서도 저장 기능이 막히지 않도록 함
    with contextlib.suppress(Exception):
        PROFILE_FILE.chmod(0o600)


def set_profile(**fields) -> dict:
    """프로필 필드 다수 저장. 빈 값은 무시."""
    data = _load_raw()
    base = data.setdefault("_base", {})
    for k, v in fields.items():
        if v is None or v == "":
            continue
        base[k] = _encrypt(str(v))
    _save_raw(data)
    return get_profile()


def set_override(site: str, **fields) -> dict:
    """사이트별 오버라이드 저장."""
    data = _load_raw()
    overrides = data.setdefault("_overrides", {})
    site_o = overrides.setdefault(site, {})
    for k, v in fields.items():
        if v is None or v == "":
            continue
        site_o[k] = _encrypt(str(v))
    _save_raw(data)
    return get_profile(site=site)


def get_profile(site: str | None = None) -> dict:
    """전체 프로필 (복호화). 사이트 주면 base + override 머지."""
    data = _load_raw()
    base = data.get("_base", {}) or {}
    out = {k: _decrypt(v) for k, v in base.items()}
    if site:
        site_o = (data.get("_overrides", {}) or {}).get(site, {}) or {}
        for k, v in site_o.items():
            out[k] = _decrypt(v)
    return out


def get_value(field: str, site: str | None = None) -> str:
    """단일 필드 조회 (복호화). site override 우선."""
    return get_profile(site=site).get(field, "")


def delete_field(field: str) -> bool:
    data = _load_raw()
    base = data.get("_base", {})
    if field not in base:
        return False
    del base[field]
    _save_raw(data)
    return True


def list_fields(site: str | None = None) -> list[str]:
    """저장된 필드 키 목록 (값 노출 X)."""
    p = get_profile(site=site)
    return [k for k, v in p.items() if v]


# ── CLI ─────────────────────────────────────────────────────────────


def _cmd_set() -> None:
    import getpass

    print("개인정보 프로필 입력 — 빈 값은 변경 안 함")
    print("(민감 필드는 자동 암호화)")
    vals = {}
    for k in [
        "name",
        "name_en",
        "email",
        "phone",
        "birth",
        "gender",
        "zipcode",
        "address",
        "address_detail",
        "default_id",
    ]:
        cur = get_value(k)
        prompt = f"  {k}"
        if cur:
            prompt += f" [현재: {cur[:6]}…]" if len(cur) > 6 else f" [현재: {cur}]"
        prompt += ": "
        v = input(prompt).strip()
        if v:
            vals[k] = v
    # default_pw 는 getpass
    cur_pw = get_value("default_pw")
    if cur_pw:
        prompt = "  default_pw [현재: 저장됨]: "
    else:
        prompt = "  default_pw: "
    pw = getpass.getpass(prompt).strip()
    if pw:
        vals["default_pw"] = pw

    if not vals:
        print("✘ 입력값 없음")
        return
    set_profile(**vals)
    print(f"✔ 저장 완료 → {PROFILE_FILE} ({len(vals)}개 필드 갱신)")


def _cmd_show(site: str | None = None) -> None:
    p = get_profile(site=site)
    if not p:
        print("저장된 프로필 없음")
        return
    label = f" (site={site})" if site else ""
    print(f"프로필{label}:")
    for k, v in sorted(p.items()):
        if "pw" in k.lower() or "password" in k.lower():
            shown = "*" * len(v)
        elif k in ("phone",) and len(v) > 4:
            shown = v[:3] + "*" * (len(v) - 6) + v[-3:]
        elif k in ("address", "address_detail") and len(v) > 10:
            shown = v[:8] + "…"
        else:
            shown = v
        print(f"  {k:<20} = {shown}")


def _cmd_set_override(site: str) -> None:
    import getpass

    print(f"[{site}] 사이트 전용 오버라이드 입력")
    nid = input("  default_id (사이트 전용): ").strip()
    pw = getpass.getpass("  default_pw (사이트 전용): ").strip()
    vals = {}
    if nid:
        vals["default_id"] = nid
    if pw:
        vals["default_pw"] = pw
    if not vals:
        print("✘ 입력값 없음")
        return
    set_override(site, **vals)
    print(f"✔ [{site}] 오버라이드 저장 완료")


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python -m scripts.form.personal_profile <set|show|delete|override> [args]")
        print("  set                              base 프로필 입력")
        print("  show [site]                      현재 값 (마스킹)")
        print("  override <site>                  사이트별 ID/PW 오버라이드")
        print("  delete <field>                   필드 삭제")
        return
    cmd = sys.argv[1]
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "set":
        _cmd_set()
    elif cmd == "show":
        _cmd_show(site=arg)
    elif cmd == "override":
        if not arg:
            print("사용법: override <site>")
            return
        _cmd_set_override(arg)
    elif cmd == "delete":
        if not arg:
            print("사용법: delete <field>")
            return
        ok = delete_field(arg)
        print("✔ 삭제" if ok else "✘ 없음")
    else:
        print(f"알 수 없는 명령: {cmd}")


if __name__ == "__main__":
    main()
