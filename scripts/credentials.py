"""자격증명 파일 관리 — data/credentials.json

환경변수 대신 JSON 파일에 사이트별 ID/PW를 저장하고 읽는다.
파일은 .gitignore에 등록되어 있어 커밋되지 않는다.

사용:
    # 저장
    from scripts.credentials import set_cred, get_cred
    set_cred("eum", id="아이디", pw="비밀번호")

    # 읽기
    cred = get_cred("eum")
    print(cred["id"], cred["pw"])

    # CLI
    python scripts/credentials.py set eum
    python scripts/credentials.py get eum
    python scripts/credentials.py list
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRED_FILE = ROOT / "data" / "credentials.json"


def _load() -> dict:
    """credentials.json 로드. 없으면 빈 dict."""
    if not CRED_FILE.exists():
        return {}
    try:
        return json.loads(CRED_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    """credentials.json 저장."""
    CRED_FILE.parent.mkdir(parents=True, exist_ok=True)
    CRED_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def set_cred(site: str, *, id: str, pw: str, **extra) -> None:
    """사이트 자격증명 저장.

    Args:
        site: 사이트 키 (예: "eum", "naver", "google")
        id:   로그인 아이디
        pw:   비밀번호
        **extra: 추가 필드 (예: otp_secret="...")
    """
    data = _load()
    data[site] = {"id": id, "pw": pw, **extra}
    _save(data)


def get_cred(site: str) -> dict:
    """사이트 자격증명 읽기.

    Returns:
        dict{"id": ..., "pw": ..., ...}
        자격증명 없으면 {"id": "", "pw": ""}
    """
    data = _load()
    return data.get(site, {"id": "", "pw": ""})


def list_sites() -> list[str]:
    """저장된 사이트 목록 반환."""
    return list(_load().keys())


def delete_cred(site: str) -> bool:
    """사이트 자격증명 삭제. 존재하면 True."""
    data = _load()
    if site not in data:
        return False
    del data[site]
    _save(data)
    return True


# ── CLI ─────────────────────────────────────────────────────────────

def _cmd_set(site: str) -> None:
    import getpass
    print(f"[{site}] 자격증명 입력")
    cred_id = input("  아이디: ").strip()
    cred_pw = getpass.getpass("  비밀번호: ").strip()
    if not cred_id or not cred_pw:
        print("✘ 아이디 또는 비밀번호가 비어 있습니다.")
        return
    set_cred(site, id=cred_id, pw=cred_pw)
    print(f"✔ [{site}] 저장 완료 → {CRED_FILE}")


def _cmd_get(site: str) -> None:
    cred = get_cred(site)
    if not cred.get("id"):
        print(f"✘ [{site}] 저장된 자격증명 없음")
        return
    # 비밀번호는 마스킹
    pw_masked = cred["pw"][:2] + "*" * (len(cred["pw"]) - 2) if len(cred["pw"]) > 2 else "**"
    print(f"✔ [{site}] id={cred['id']}  pw={pw_masked}")


def _cmd_list() -> None:
    sites = list_sites()
    if not sites:
        print("저장된 자격증명 없음")
        return
    print(f"저장된 사이트 ({len(sites)}개):")
    for s in sites:
        cred = get_cred(s)
        print(f"  {s:<16} id={cred.get('id', '')}")


def _cmd_delete(site: str) -> None:
    if delete_cred(site):
        print(f"✔ [{site}] 삭제 완료")
    else:
        print(f"✘ [{site}] 없음")


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python scripts/credentials.py <set|get|list|delete> [사이트]")
        print("  set eum       EUM 자격증명 입력/저장")
        print("  get eum       EUM 자격증명 확인 (비밀번호 마스킹)")
        print("  list          저장된 사이트 목록")
        print("  delete eum    EUM 자격증명 삭제")
        return

    cmd = sys.argv[1]
    site = sys.argv[2] if len(sys.argv) > 2 else ""

    match cmd:
        case "set":
            if not site:
                print("사용법: python scripts/credentials.py set <사이트>")
                return
            _cmd_set(site)
        case "get":
            if not site:
                print("사용법: python scripts/credentials.py get <사이트>")
                return
            _cmd_get(site)
        case "list":
            _cmd_list()
        case "delete":
            if not site:
                print("사용법: python scripts/credentials.py delete <사이트>")
                return
            _cmd_delete(site)
        case _:
            print(f"알 수 없는 명령: {cmd}")


if __name__ == "__main__":
    main()
