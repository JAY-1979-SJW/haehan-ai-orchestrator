"""1PC 1라이선스 체크 — 서버 없이 로컬에서 검증하는 오프라인 방식.

원리:
  1. 고객 PC에서 get_machine_id()로 이 PC 고유값(해시)을 뽑는다.
  2. 고객이 결제 후 이 값을 판매자(우리)에게 보내면, 우리가
     generate_license_key()로 "이 PC 전용" 라이선스 키를 만들어 발급한다.
  3. 앱은 verify_license()로 "이 키가 이 PC의 machine_id로 서명된 게 맞는지"만
     검증한다 — 인터넷 연결이나 라이선스 서버가 필요 없다(오프라인 데스크톱
     앱이라 서버 운영 부담을 만들지 않기 위한 선택).

한계(정직하게 명시):
  - _SECRET을 리버스엔지니어링하면 키 생성기를 복제할 수 있다. 완벽한
    복제방지가 아니라 "일반 사용자가 실수로/의도적으로 재배포하는 것을
    막는" 수준의 방어다. 강력한 DRM이 필요하면 서버 기반 활성화로 바꿔야
    하는데, 그건 별도 서버 인프라 비용이 든다.
  - 코드 서명(exe에 인증서 서명)은 이것과 별개이며 인증서 구매가 필요해
    아직 미착수 — Windows SmartScreen 경고는 라이선스 체크와 무관하게 뜬다.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import platform
import subprocess
import sys

# ⚠️ 실제 배포 전 반드시 교체할 것 — 이 값이 노출되면 키 생성기를 복제당한다.
# (환경변수로 오버라이드 가능하게 해서, 배포 빌드마다 다른 값을 주입할 수 있게 함)
_SECRET = os.environ.get("LICENSE_SIGNING_SECRET", "haehan-ai-blog-autopost-CHANGE-ME-BEFORE-SHIP")


def get_machine_id() -> str:
    """이 PC를 식별하는 안정적인 해시값. Windows는 MachineGuid, 그 외는 platform.node() 폴백."""
    raw = ""
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            for line in out.stdout.splitlines():
                if "MachineGuid" in line:
                    raw = line.strip().split()[-1]
                    break
        except Exception:
            raw = ""
    if not raw:
        raw = platform.node() + platform.machine()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def generate_license_key(machine_id: str, secret: str | None = None) -> str:
    """판매자 전용 — 고객의 machine_id로 라이선스 키를 발급한다."""
    sig = hmac.new((secret or _SECRET).encode("utf-8"), machine_id.encode("utf-8"), hashlib.sha256).hexdigest()[:20]
    return f"{machine_id}-{sig}"


def verify_license(license_key: str, secret: str | None = None) -> bool:
    """이 PC에서 이 라이선스 키가 유효한지 확인."""
    if not license_key or "-" not in license_key:
        return False
    machine_id, _, sig = license_key.rpartition("-")
    if machine_id != get_machine_id():
        return False
    expected = generate_license_key(machine_id, secret=secret)
    _, _, expected_sig = expected.rpartition("-")
    return hmac.compare_digest(sig, expected_sig)
