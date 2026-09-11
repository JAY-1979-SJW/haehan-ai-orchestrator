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
import logging
import os
import platform
import subprocess
import sys

_log = logging.getLogger(__name__)

# 보안 리뷰 지적사항(2026-09-12) 반영: 소스에 실사용 가능한 기본 시크릿을 절대
# 두지 않는다(하드코딩된 기본값은 리포를 본 사람이 그대로 키 생성기를 복제할
# 수 있다). LICENSE_SIGNING_SECRET 환경변수가 없으면 "동작하는 대체값"으로
# 넘어가지 않고 항상 실패(fail-closed)한다 — 배포 패키징 시에만 이 환경변수를
# 주입하고, 그 실제 값은 절대 커밋하지 않는다.
_SECRET = os.environ.get("LICENSE_SIGNING_SECRET") or None
if _SECRET is None:
    _log.warning(
        "LICENSE_SIGNING_SECRET 환경변수가 없습니다 — 라이선스 발급/검증이 "
        "전부 실패로 처리됩니다(fail-closed, 의도된 동작). 실제 배포 패키징 "
        "시 이 환경변수를 반드시 주입하세요."
    )


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
    """판매자 전용 — 고객의 machine_id로 라이선스 키를 발급한다.

    secret 인자도 없고 LICENSE_SIGNING_SECRET 환경변수도 없으면 발급 자체를
    거부한다(RuntimeError) — 대체 시크릿으로 조용히 동작하지 않는다.
    """
    real_secret = secret or _SECRET
    if not real_secret:
        raise RuntimeError("LICENSE_SIGNING_SECRET 환경변수가 없어 라이선스를 발급할 수 없습니다.")
    sig = hmac.new(real_secret.encode("utf-8"), machine_id.encode("utf-8"), hashlib.sha256).hexdigest()[:20]
    return f"{machine_id}-{sig}"


def verify_license(license_key: str, secret: str | None = None) -> bool:
    """이 PC에서 이 라이선스 키가 유효한지 확인. 시크릿 미설정이면 항상 False(fail-closed)."""
    if not (secret or _SECRET):
        return False
    if not license_key or "-" not in license_key:
        return False
    machine_id, _, sig = license_key.rpartition("-")
    if machine_id != get_machine_id():
        return False
    expected = generate_license_key(machine_id, secret=secret)
    _, _, expected_sig = expected.rpartition("-")
    return hmac.compare_digest(sig, expected_sig)
