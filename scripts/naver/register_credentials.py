"""네이버 자격증명 안전 등록 (대화형).

비밀번호는 getpass로 화면에 표시 안 됨.
저장 위치: data/credentials.json (Fernet 암호화, 마스터 키는 Windows 자격 증명 관리자)

사용:
  python scripts/naver/register_credentials.py
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.auth.credentials import CRED_FILE
from scripts.naver.common.auth import _load_credentials, save_credentials


def main():
    print("=" * 60)
    print("  네이버 자격증명 등록")
    print("=" * 60)
    print(f"  저장 위치: {CRED_FILE}")
    print("  보안: 비밀번호 Fernet 암호화 + 마스터 키는 Windows 자격 증명 관리자(같은 Windows 계정만 복호화)")
    print()

    existing_id, existing_pw = _load_credentials()
    if existing_id:
        print(f"  기존 등록된 ID: {existing_id}")
        ans = input("  덮어쓰시겠습니까? (y/N) ").strip().lower()
        if ans != "y":
            print("  취소됨.")
            return

    naver_id = input("  네이버 ID: ").strip()
    if not naver_id:
        print("  ID 없음 — 취소")
        return

    naver_pw = getpass.getpass("  네이버 PW (입력 시 화면에 표시되지 않음): ").strip()
    if not naver_pw:
        print("  PW 없음 — 취소")
        return

    # 확인
    naver_pw2 = getpass.getpass("  PW 다시 입력 (확인): ").strip()
    if naver_pw != naver_pw2:
        print("  PW 불일치 — 취소")
        return

    path = save_credentials(naver_id, naver_pw)
    print()
    print(f"  ✓ 저장 완료: {path}")
    print(f"  ✓ ID: {naver_id}  PW: ******* ({len(naver_pw)}자)")
    print()
    print("  이제 자동 로그인 가능합니다:")
    print("    from scripts.naver.blog.writer import write_post")
    print("    from scripts.browser.cdp.connection import get_page")
    print("    write_post(get_page(), title='...', body='...')")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n중단됨")
