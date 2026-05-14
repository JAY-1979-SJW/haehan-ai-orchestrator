"""Google 자격증명 안전 등록 (대화형).

비밀번호는 getpass로 화면에 표시 안 됨.
저장 위치: data/.env_google (권한 0o600, gitignore 등록 권장)

사용:
  python scripts/google/register_credentials.py
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.google.auth import save_credentials, _load_credentials, ENV_FILE


def main():
    print("=" * 60)
    print("  구글 자격증명 등록")
    print("=" * 60)
    print(f"  저장 위치: {ENV_FILE}")
    print(f"  보안: 파일 권한 0o600 (소유자 전용) + gitignore 권장")
    print()
    print("  ⚠ Google은 2단계 인증(2FA)이 거의 필수입니다.")
    print("     ID/PW 입력 후 휴대폰/OTP 확인 화면이 뜨면 직접 처리하세요.")
    print()

    existing_id, existing_pw = _load_credentials()
    if existing_id:
        print(f"  기존 등록된 ID: {existing_id}")
        ans = input("  덮어쓰시겠습니까? (y/N) ").strip().lower()
        if ans != "y":
            print("  취소됨.")
            return

    google_id = input("  구글 ID(이메일): ").strip()
    if not google_id:
        print("  ID 없음 — 취소")
        return
    if "@" not in google_id:
        google_id += "@gmail.com"
        print(f"  → 자동 보정: {google_id}")

    google_pw = getpass.getpass("  구글 PW (입력 시 화면에 표시되지 않음): ").strip()
    if not google_pw:
        print("  PW 없음 — 취소")
        return

    google_pw2 = getpass.getpass("  PW 다시 입력 (확인): ").strip()
    if google_pw != google_pw2:
        print("  PW 불일치 — 취소")
        return

    path = save_credentials(google_id, google_pw)
    print()
    print(f"  ✓ 저장 완료: {path}")
    print(f"  ✓ ID: {google_id}  PW: ******* ({len(google_pw)}자)")
    print()
    print("  이제 자동 로그인 가능합니다:")
    print("    from scripts.google.auth import ensure_google_login")
    print("    from scripts.web_connector import get_page")
    print("    ensure_google_login(get_page())")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n중단됨")
