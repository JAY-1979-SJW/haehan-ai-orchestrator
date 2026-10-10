"""자격증명 통합 저장소 — data/credentials.json (암호화)

- pw 는 Fernet 대칭 암호화 (cryptography.Fernet)
- 마스터 키: Windows 자격 증명 관리자(keyring, 서비스 haehan-ai/credentials) — 같은 OS 계정만 복호화.
  기존 data/.cred.key 가 있으면 첫 사용 시 keyring 으로 이전하고 .cred.key.migrated 로 이름만 바꾼다(삭제 안 함).
  keyring 을 못 쓰면 오류로 중단(fail-closed). 개발용은 HAEHAN_CRED_KEY_BACKEND=file 로 명시할 때만
  data/.cred.key 파일 방식(옛 동작)을 쓴다.
- pw_enc 필드에 토큰 저장; 로드 시 자동 복호화
- 평문 pw 가 있으면 첫 로드 시 자동으로 암호화하고 재저장 (마이그레이션)
- .env_naver / .env_google 파일이 있으면 첫 로드 시 흡수 후 archive

사용:
    from scripts.auth.credentials import set_cred, get_cred
    set_cred("eum", id="아이디", pw="비밀번호")
    cred = get_cred("eum")   # {"id": ..., "pw": ...}  pw 자동 복호화

CLI:
    python scripts/auth/credentials.py set <site>
    python scripts/auth/credentials.py get <site>
    python scripts/auth/credentials.py list
    python scripts/auth/credentials.py delete <site>
    python scripts/auth/credentials.py migrate    # .env_* 파일 흡수
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_orchestrator.paths.runtime import atomic_write_bytes, data_dir  # noqa: E402
from ai_orchestrator.core.security_utils import mask_identifier  # noqa: E402

CRED_FILE = data_dir() / "credentials.json"
KEY_FILE = data_dir() / ".cred.key"  # keyring 이전 원본 / HAEHAN_CRED_KEY_BACKEND=file 개발용 경로
KEY_SERVICE = "haehan-ai/credentials"
KEY_ACCOUNT = "master-key"


class CredentialKeyError(RuntimeError):
    """마스터 키를 OS 자격 증명 관리자에서 다룰 수 없을 때. 메시지에 키·비밀번호 값은 넣지 않는다."""


# 레거시 평문 파일 (마이그레이션 후 archive)
_LEGACY_ENV_FILES = {
    "naver": data_dir() / ".env_naver",
}
_LEGACY_ENV_KEYS = {
    "naver": ("NAVER_ID", "NAVER_PW"),
}
_PASSWORD_LOGIN_DISABLED_SITES = {"google"}


def _is_password_login_disabled(site: str) -> bool:
    return (site or "").strip().lower() in _PASSWORD_LOGIN_DISABLED_SITES


def _key_backend() -> str:
    """'file' 은 환경변수로 명시했을 때만. 기본은 OS 자격 증명 관리자(keyring)."""
    return "file" if os.environ.get("HAEHAN_CRED_KEY_BACKEND", "").strip().lower() == "file" else "keyring"


def _keyring_module():
    try:
        import keyring  # type: ignore
    except ImportError as e:
        raise CredentialKeyError("keyring 패키지가 없어 마스터 키를 안전하게 보관할 수 없음") from e
    return keyring


def _file_key() -> bytes:
    """옛 방식: data/.cred.key. 없으면 신규 생성."""
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes().strip()
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    atomic_write_bytes(KEY_FILE, key)
    # chmod 권한 강화 실패는 무시해도 자격증명 값 노출이나 보안 우회로 이어지지 않음
    with contextlib.suppress(Exception):
        KEY_FILE.chmod(0o600)
    return key


def _all_entries_decrypt_with(key: bytes) -> bool:
    """credentials.json 의 모든 pw_enc 가 이 키로 풀리는지(값은 다루지 않고 성공 여부만)."""
    if not CRED_FILE.exists():
        return True
    try:
        data = json.loads(CRED_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 깨진 파일이면 이전 후 검증을 통과시키지 않아 원본 키 파일을 지우지/바꾸지 않는다(fail-safe)
        return False
    f = Fernet(key)
    for entry in data.values():
        token = entry.get("pw_enc") if isinstance(entry, dict) else None
        if token:
            try:
                f.decrypt(token.encode("ascii"))
            except (InvalidToken, ValueError):
                return False
    return True


def _get_or_create_key() -> bytes:
    """마스터 키 로드. keyring 우선 → 없으면 .cred.key 이전 → 둘 다 없으면 신규 생성 후 keyring 저장."""
    if _key_backend() == "file":
        return _file_key()
    kr = _keyring_module()
    try:
        stored = kr.get_password(KEY_SERVICE, KEY_ACCOUNT)
    except (
        Exception
    ) as e:  # 자격 증명 관리자 접근 실패(잠김/권한): 파일로 조용히 넘어가지 않고 중단(fail-closed), 원인 예외에 값 없음
        raise CredentialKeyError("OS 자격 증명 관리자에 접근할 수 없음") from e
    if stored:
        return stored.encode("ascii")
    try:
        if KEY_FILE.exists():
            key = KEY_FILE.read_bytes().strip()
            migrated = True
        else:
            key = Fernet.generate_key()
            migrated = False
        kr.set_password(KEY_SERVICE, KEY_ACCOUNT, key.decode("ascii"))
        if kr.get_password(KEY_SERVICE, KEY_ACCOUNT) != key.decode("ascii"):
            raise CredentialKeyError("마스터 키 저장 확인에 실패")
    except CredentialKeyError:
        raise
    except Exception as e:  # 저장 실패도 fail-closed. 원본 키 파일은 그대로 둔다
        raise CredentialKeyError("OS 자격 증명 관리자에 마스터 키를 저장할 수 없음") from e
    if migrated and _all_entries_decrypt_with(key):
        # 삭제하지 않고 이름만 바꾼다. 사용자가 확인 후 직접 지운다.
        with contextlib.suppress(OSError):
            KEY_FILE.rename(KEY_FILE.with_name(KEY_FILE.name + ".migrated"))
    return key


def _fernet() -> Fernet:
    return Fernet(_get_or_create_key())


def _encrypt(pw: str) -> str:
    if not pw:
        return ""
    return _fernet().encrypt(pw.encode("utf-8")).decode("ascii")


def _decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""


def _read_legacy_env(site: str) -> dict:
    """data/.env_<site> 평문 파일에서 ID/PW 추출."""
    fp = _LEGACY_ENV_FILES.get(site)
    if not fp or not fp.exists():
        return {}
    id_key, pw_key = _LEGACY_ENV_KEYS[site]
    out = {}
    try:
        for line in fp.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k == id_key:
                out["id"] = v
            elif k == pw_key:
                out["pw"] = v
    except Exception:  # noqa: BLE001 - 자격증명 통합 저장소(Fernet 암호화) - chmod 권한설정 실패는 무시(파일은 정상 저장), JSON/레거시 파싱 실패는 빈 dict로 폴백(자격증명 없음으로 처리되어 인증 실패 방향), 예외 메시지에 실제 pw 값 미노출
        return {}
    return out


def _load_raw() -> dict:
    if not CRED_FILE.exists():
        return {}
    try:
        return json.loads(CRED_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - 자격증명 통합 저장소(Fernet 암호화) - chmod 권한설정 실패는 무시(파일은 정상 저장), JSON/레거시 파싱 실패는 빈 dict로 폴백(자격증명 없음으로 처리되어 인증 실패 방향), 예외 메시지에 실제 pw 값 미노출
        return {}


def _save_raw(data: dict) -> None:
    """같은 폴더 tmp 에 쓰고 fsync 후 os.replace — 쓰는 도중 끊겨도 원본이 안 손상된다
    (2026-10-10, licenses.json 손상 사고와 같은 위험을 자격증명 파일에서도 막기 위해
    atomic_write_text 보다 한 단계 더 — fsync 로 OS 캐시에만 있던 내용까지 디스크에
    확실히 반영하고, 실패하면 tmp 를 지워 흔적을 안 남긴다)."""
    CRED_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    tmp = CRED_FILE.with_name(f"{CRED_FILE.name}.tmp-{os.getpid()}")
    try:
        with open(tmp, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(CRED_FILE)
    except Exception:
        with contextlib.suppress(Exception):
            tmp.unlink()
        raise
    # chmod 권한 강화 실패는 무시해도 자격증명 값 노출이나 보안 우회로 이어지지 않음
    with contextlib.suppress(Exception):
        CRED_FILE.chmod(0o600)


def _normalize(data: dict) -> tuple[dict, bool]:
    """평문 pw → pw_enc 마이그레이션. 변경 여부 반환."""
    changed = False
    for site, rec in list(data.items()):
        if not isinstance(rec, dict):
            continue
        if rec.get("pw"):
            # 평문이 있으면 암호화로 옮김
            rec["pw_enc"] = _encrypt(rec["pw"])
            del rec["pw"]
            changed = True
        elif "pw" in rec and not rec["pw"]:
            del rec["pw"]
            changed = True
    return data, changed


def _absorb_legacy(data: dict) -> bool:
    """레거시 .env_* 파일에서 자격증명 흡수. 변경 여부 반환."""
    changed = False
    for site in _LEGACY_ENV_FILES:
        if site in data and data[site].get("pw_enc"):
            continue  # 이미 통합 저장소에 있음
        legacy = _read_legacy_env(site)
        if legacy.get("id") and legacy.get("pw"):
            data[site] = {
                "id": legacy["id"],
                "pw_enc": _encrypt(legacy["pw"]),
            }
            changed = True
    return changed


def _load() -> dict:
    """credentials.json 로드 + 자동 마이그레이션."""
    data = _load_raw()
    data, c1 = _normalize(data)
    c2 = _absorb_legacy(data)
    if c1 or c2:
        _save_raw(data)
    return data


def set_cred(site: str, *, id: str, pw: str, **extra) -> None:
    """사이트 자격증명 저장 (pw 자동 암호화)."""
    if _is_password_login_disabled(site):
        raise ValueError(f"password credential storage is disabled for {site}")
    data = _load()
    rec = {"id": id, "pw_enc": _encrypt(pw)}
    rec.update(extra)
    data[site] = rec
    _save_raw(data)


def get_cred(site: str) -> dict:
    """사이트 자격증명 읽기. pw 자동 복호화."""
    if _is_password_login_disabled(site):
        return {"id": "", "pw": ""}
    data = _load()
    rec = data.get(site, {})
    if not rec:
        return {"id": "", "pw": ""}
    out = {"id": rec.get("id", ""), "pw": _decrypt(rec.get("pw_enc", ""))}
    for k, v in rec.items():
        if k not in ("id", "pw_enc"):
            out[k] = v
    return out


def get_naver_cred(naver_id: str) -> dict:
    """네이버 계정 ID로 자격증명 조회.

    탐색 순서: naver:{id} → naver_{id} → naver (기본 계정)
    반환: {"id": ..., "pw": ...}  pw가 없으면 빈 문자열.
    """
    for key in (f"naver:{naver_id}", f"naver_{naver_id}", "naver"):
        cred = get_cred(key)
        if cred.get("pw"):
            if key == "naver" and cred.get("id") and cred["id"] != naver_id:
                continue  # 기본 계정 id가 요청 id와 다르면 건너뜀
            return {"id": naver_id, "pw": cred["pw"]}
    return {"id": naver_id, "pw": ""}


def list_sites() -> list[str]:
    return [site for site in _load() if not _is_password_login_disabled(site)]


def delete_cred(site: str) -> bool:
    data = _load()
    if site not in data:
        return False
    del data[site]
    _save_raw(data)
    return True


def migrate_legacy() -> dict:
    """레거시 .env_* 파일 흡수 + 아카이브."""
    data = _load()  # 흡수는 _load 내부에서 자동
    archived = []
    for site, fp in _LEGACY_ENV_FILES.items():
        if fp.exists() and site in data and data[site].get("pw_enc"):
            archive_dir = data_dir() / "_legacy_creds"
            archive_dir.mkdir(parents=True, exist_ok=True)
            target = archive_dir / fp.name
            try:
                fp.rename(target)
                archived.append(str(target))
            except Exception:  # noqa: BLE001 - chmod 권한 강화/레거시 파일 아카이브 이동 실패는 무시해도 자격증명 값 노출이나 보안 우회로 이어지지 않음
                pass
    return {"sites": list(data.keys()), "archived": archived}


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
    print(f"✔ [{site}] 저장 완료 (암호화) → {CRED_FILE}")


def _cmd_get(site: str) -> None:
    cred = get_cred(site)
    if not cred.get("id"):
        print(f"✘ [{site}] 저장된 자격증명 없음")
        return
    pw = cred.get("pw", "")
    pw_masked = pw[:2] + "*" * max(0, len(pw) - 2) if len(pw) > 2 else "**"
    cred["id"] = mask_identifier(cred["id"])
    print(f"✔ [{site}] id={cred['id']}  pw={pw_masked}  (복호화 OK)")


def _cmd_list() -> None:
    sites = list_sites()
    if not sites:
        print("저장된 자격증명 없음")
        return
    print(f"저장된 사이트 ({len(sites)}개):")
    for s in sites:
        cred = get_cred(s)
        cred["id"] = mask_identifier(cred.get("id", ""))
        enc_ok = "✓" if cred.get("pw") else "✘복호화실패"
        print(f"  {s:<16} id={cred.get('id', ''):<32} [{enc_ok}]")


def _cmd_delete(site: str) -> None:
    if delete_cred(site):
        print(f"✔ [{site}] 삭제 완료")
    else:
        print(f"✘ [{site}] 없음")


def _cmd_migrate() -> None:
    result = migrate_legacy()
    print(f"✔ 통합 저장소 사이트: {result['sites']}")
    if result["archived"]:
        print("✔ 레거시 파일 아카이브:")
        for a in result["archived"]:
            print(f"    {a}")
    else:
        print("  (이동된 레거시 파일 없음)")


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python scripts/auth/credentials.py <set|get|list|delete|migrate> [사이트]")
        print("  set <site>     자격증명 입력/저장 (암호화)")
        print("  get <site>     자격증명 확인 (마스킹)")
        print("  list           저장된 사이트 목록")
        print("  delete <site>  삭제")
        print("  migrate        레거시 .env_* 파일 흡수 후 아카이브")
        return

    cmd = sys.argv[1]
    site = sys.argv[2] if len(sys.argv) > 2 else ""

    match cmd:
        case "set":
            if not site:
                print("사용법: set <site>")
                return
            _cmd_set(site)
        case "get":
            if not site:
                print("사용법: get <site>")
                return
            _cmd_get(site)
        case "list":
            _cmd_list()
        case "delete":
            if not site:
                print("사용법: delete <site>")
                return
            _cmd_delete(site)
        case "migrate":
            _cmd_migrate()
        case _:
            print(f"알 수 없는 명령: {cmd}")


if __name__ == "__main__":
    main()
