"""인증 세션 저장/복원 — 로그인 후 상태를 캡처해 재사용.

저장 대상:
  - 쿠키 (전체 또는 도메인 필터)
  - localStorage (도메인별)
  - sessionStorage (도메인별)
  - 현재 URL/제목 (참고용)

저장 위치: data/sessions/<host>.json (Fernet 암호화)

사용:
    from scripts.auth.auth_session import save_session, restore_session
    save_session('eum.cw.or.kr', page)           # 사용자 로그인 후 1회
    restore_session('eum.cw.or.kr', page)        # 새 세션에서 복원

CLI:
    python scripts/entry/cdp_cli.py session save <site>
    python scripts/entry/cdp_cli.py session load <site>
    python scripts/entry/cdp_cli.py session list
    python scripts/entry/cdp_cli.py session delete <site>
"""

from __future__ import annotations

import contextlib
import json
import sys
from datetime import datetime
from pathlib import Path

from cryptography.fernet import InvalidToken

from ai_orchestrator.paths.runtime import atomic_write_text, data_dir
from scripts.common.app_paths import repo_root

ROOT = repo_root()
SESSIONS_DIR = data_dir() / "sessions"


def _fernet():
    from scripts.auth.credentials import _fernet as f

    return f()


def _encrypt(s: str) -> str:
    return _fernet().encrypt(s.encode("utf-8")).decode("ascii")


def _decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""


def _capture_storage(page, host: str) -> dict:
    """현재 페이지의 localStorage + sessionStorage 캡처."""
    js = """
    () => {
      const out = {local: {}, session: {}};
      try { for (let i=0; i<localStorage.length; i++) {
        const k = localStorage.key(i);
        out.local[k] = localStorage.getItem(k);
      }} catch(e) {}
      try { for (let i=0; i<sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        out.session[k] = sessionStorage.getItem(k);
      }} catch(e) {}
      return out;
    }
    """
    try:
        return page.evaluate(js) or {"local": {}, "session": {}}
    except Exception:  # noqa: BLE001 - 브라우저 세션(쿠키/storage) 저장/복원 유틸 - CLAUDE.md 명시된 로그인세션 보존 정책에 따라 저장/복원만 수행, 로그아웃/쿠키삭제 없음. chmod 실패는 이미 암호화된 파일이라 best-effort
        return {"local": {}, "session": {}}


def save_session(host: str, page, *, host_filter: bool = True) -> Path:
    """현재 page의 쿠키 + storage를 host용 세션으로 저장.

    Args:
        host: 사이트 호스트명 (예: eum.cw.or.kr)
        page: Playwright Page
        host_filter: True 면 해당 호스트 쿠키만 저장
    """
    ctx = page.context
    cookies = ctx.cookies()
    if host_filter:
        cookies = [c for c in cookies if host in (c.get("domain") or "")]

    storage = _capture_storage(page, host)

    bundle = {
        "host": host,
        "saved_at": datetime.now().isoformat(),
        "url": page.url,
        "title": (page.title() or "")[:200],
        "cookies": cookies,
        "localStorage": storage.get("local", {}),
        "sessionStorage": storage.get("session", {}),
    }
    # 통째로 암호화 (cookie value 가 민감)
    payload = _encrypt(json.dumps(bundle, ensure_ascii=False))

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    fp = SESSIONS_DIR / f"{host}.json"
    atomic_write_text(
        fp,
        json.dumps(
            {
                "host": host,
                "saved_at": bundle["saved_at"],
                "cookie_count": len(cookies),
                "local_keys": len(storage.get("local", {})),
                "session_keys": len(storage.get("session", {})),
                "encrypted_bundle": payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    # chmod 실패는 이미 암호화된 파일이라 best-effort (저장/복원만 수행, 로그아웃/쿠키삭제 없음)
    with contextlib.suppress(Exception):
        fp.chmod(0o600)
    return fp


def _load_bundle(host: str) -> dict | None:
    fp = SESSIONS_DIR / f"{host}.json"
    if not fp.exists():
        return None
    try:
        meta = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 브라우저 세션(쿠키/storage) 저장/복원 유틸 - CLAUDE.md 명시된 로그인세션 보존 정책에 따라 저장/복원만 수행, 로그아웃/쿠키삭제 없음. chmod 실패는 이미 암호화된 파일이라 best-effort
        return None
    payload = meta.get("encrypted_bundle", "")
    if not payload:
        return None
    plain = _decrypt(payload)
    if not plain:
        return None
    try:
        return json.loads(plain)
    except Exception:  # noqa: BLE001 - 브라우저 세션(쿠키/storage) 저장/복원 유틸 - CLAUDE.md 명시된 로그인세션 보존 정책에 따라 저장/복원만 수행, 로그아웃/쿠키삭제 없음. chmod 실패는 이미 암호화된 파일이라 best-effort
        return None


def restore_session(host: str, page) -> dict:
    """저장된 세션을 현재 컨텍스트에 복원.

    Returns:
        {ok, restored_cookies, restored_local, restored_session, saved_at}
    """
    bundle = _load_bundle(host)
    if not bundle:
        return {"ok": False, "reason": "no_session_saved"}

    ctx = page.context
    # 쿠키 복원
    try:
        ctx.add_cookies(bundle.get("cookies", []))
    except Exception as e:  # noqa: BLE001 - 브라우저 세션(쿠키/storage) 저장/복원 유틸 - CLAUDE.md 명시된 로그인세션 보존 정책에 따라 저장/복원만 수행, 로그아웃/쿠키삭제 없음. chmod 실패는 이미 암호화된 파일이라 best-effort
        return {"ok": False, "reason": f"cookie_restore_failed: {e}"}

    # storage 복원 — 도메인 페이지 필요
    js = """
    ([local, session]) => {
      try { for (const [k, v] of Object.entries(local)) localStorage.setItem(k, v); } catch(e) {}
      try { for (const [k, v] of Object.entries(session)) sessionStorage.setItem(k, v); } catch(e) {}
      return true;
    }
    """
    try:
        # 같은 호스트에 있어야 storage 복원 가능
        if host in (page.url or ""):
            page.evaluate(js, [bundle.get("localStorage", {}), bundle.get("sessionStorage", {})])
    except Exception:  # noqa: BLE001 - 브라우저 세션(쿠키/storage) 저장/복원 유틸 - CLAUDE.md 명시된 로그인세션 보존 정책에 따라 저장/복원만 수행, 로그아웃/쿠키삭제 없음. chmod 실패는 이미 암호화된 파일이라 best-effort
        # storage 실패해도 쿠키만으로 로그인 유지될 수 있음
        pass

    return {
        "ok": True,
        "restored_cookies": len(bundle.get("cookies", [])),
        "restored_local": len(bundle.get("localStorage", {})),
        "restored_session": len(bundle.get("sessionStorage", {})),
        "saved_at": bundle.get("saved_at"),
    }


def list_sessions() -> list[dict]:
    if not SESSIONS_DIR.exists():
        return []
    out = []
    for fp in sorted(SESSIONS_DIR.glob("*.json")):
        try:
            meta = json.loads(fp.read_text(encoding="utf-8"))
            out.append(
                {
                    "host": meta.get("host", fp.stem),
                    "saved_at": meta.get("saved_at"),
                    "cookie_count": meta.get("cookie_count", 0),
                    "local_keys": meta.get("local_keys", 0),
                    "session_keys": meta.get("session_keys", 0),
                }
            )
        except Exception:  # noqa: BLE001 - 브라우저 세션(쿠키/storage) 저장/복원 유틸 - CLAUDE.md 명시된 로그인세션 보존 정책에 따라 저장/복원만 수행, 로그아웃/쿠키삭제 없음. chmod 실패는 이미 암호화된 파일이라 best-effort
            continue
    return out


def delete_session(host: str) -> bool:
    fp = SESSIONS_DIR / f"{host}.json"
    if fp.exists():
        fp.unlink()
        return True
    return False


# ── CLI 헬퍼 (cdp_client 에서 호출) ────────────────────────────────


def cli_save(host: str) -> None:
    from scripts.browser.cdp.connection import get_page

    page = get_page()
    fp = save_session(host, page)
    info = json.loads(fp.read_text(encoding="utf-8"))
    print(f"✔ 세션 저장: {fp}")
    print(f"  쿠키: {info['cookie_count']}  localStorage: {info['local_keys']}  sessionStorage: {info['session_keys']}")


def cli_load(host: str) -> None:
    from scripts.browser.cdp.connection import get_page

    page = get_page()
    # 같은 호스트로 먼저 이동해야 storage 복원 가능
    if host not in (page.url or ""):
        page.goto(f"https://{host}/", timeout=15000)
        # 로드 대기 실패해도 계속 진행 (저장/복원만 수행, 로그아웃/쿠키삭제 없음)
        with contextlib.suppress(Exception):
            page.wait_for_load_state("domcontentloaded", timeout=5000)
    r = restore_session(host, page)
    if r["ok"]:
        print(f"✔ 세션 복원 ({r['saved_at']} 저장본)")
        print(
            f"  쿠키 {r['restored_cookies']}  localStorage {r['restored_local']}  sessionStorage {r['restored_session']}"
        )
        page.reload()
    else:
        print(f"✘ 복원 실패: {r['reason']}")


def cli_list() -> None:
    items = list_sessions()
    if not items:
        print("저장된 세션 없음")
        return
    print(f"저장된 세션 {len(items)}개:")
    for it in items:
        print(
            f"  {it['host']:<24} saved={it['saved_at']}  cookies={it['cookie_count']}  ls={it['local_keys']}  ss={it['session_keys']}"
        )


def cli_delete(host: str) -> None:
    if delete_session(host):
        print(f"✔ 삭제: {host}")
    else:
        print(f"✘ 없음: {host}")


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python -m scripts.auth.auth_session <save|load|list|delete> [host]")
        return
    cmd = sys.argv[1]
    host = sys.argv[2] if len(sys.argv) > 2 else ""
    if cmd == "save":
        cli_save(host)
    elif cmd == "load":
        cli_load(host)
    elif cmd == "list":
        cli_list()
    elif cmd == "delete":
        cli_delete(host)
    else:
        print(f"알 수 없는 명령: {cmd}")


if __name__ == "__main__":
    main()
