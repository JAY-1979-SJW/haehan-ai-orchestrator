"""판매자(우리) 전용 — 고객이 보낸 PC 코드로 라이선스 키를 발급한다.

⚠️ 이 파일은 고객에게 배포하지 않는다(패키징 시 exe에서 제외).
   고객 결제 확인 후, 고객이 setup_gui.py의 "라이선스 인증" 창에서 복사해
   보낸 PC 코드를 아래처럼 입력해서 키를 만들어 회신한다.

사용:
    python generate_license.py <고객PC코드>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.license_check import generate_license_key


def main() -> None:
    if len(sys.argv) != 2:
        print("사용: python generate_license.py <고객PC코드>")
        return
    machine_id = sys.argv[1].strip()
    key = generate_license_key(machine_id)
    print(f"라이선스 키: {key}")


if __name__ == "__main__":
    main()
