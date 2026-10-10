"""EUM 단말기 운용 상태 모니터링.

data/eum_all_devices_complete.json 로드 후:
- 통신단절 단말기 목록
- 미사용(설치일수 과다) 단말기 목록
- 준공 임박 단말기 목록 (철거일 설정된 것)

사용:
    python scripts/eum/monitor.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.common.logger import get_logger  # noqa: E402
from scripts.common.op_log import op_context  # noqa: E402

log = get_logger(__name__)


def _eum_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("eum")


DATA_DIR = _eum_dir()
DEVICES_FILE = DATA_DIR / "eum_all_devices_complete.json"

# 미사용 임계값 (설치일수 기준)
UNUSED_THRESHOLD_DAYS = 180  # 6개월 이상 설치 → 장기 모니터링 대상
# 준공 임박 임계값 (철거 예정일까지 남은 일수)
DEMOLITION_WARNING_DAYS = 30


def _load_devices() -> list[dict]:
    """data/eum_all_devices_complete.json 로드."""
    if not DEVICES_FILE.exists():
        log.warning("단말기 데이터 파일 없음: %s", DEVICES_FILE)
        return []
    try:
        data = json.loads(DEVICES_FILE.read_text(encoding="utf-8"))
        # 최상위가 list 또는 dict{"devices": [...]} 형태 모두 처리
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # 추출기는 all_devices 키로 저장 — devices/data/all_devices 순으로 처리
            return data.get("devices") or data.get("all_devices") or data.get("data") or []
        return []
    except Exception as e:  # noqa: BLE001 - EUM 단말기 데이터 읽기전용 조회/파싱 — API 응답 파싱 실패 시 빈 리스트/None으로 안전 폴백, 데이터 조회만 하고 쓰기 없음
        log.error("단말기 데이터 로드 실패: %s", e)
        return []


def _parse_days(val) -> int | None:
    """설치일수 파싱. 숫자 또는 '123일' 형식 처리."""
    if val is None:
        return None
    try:
        return int(str(val).replace("일", "").replace(",", "").strip())
    except Exception:  # noqa: BLE001 - EUM 단말기 데이터 읽기전용 조회/파싱 — API 응답 파싱 실패 시 빈 리스트/None으로 안전 폴백, 데이터 조회만 하고 쓰기 없음
        return None


def _parse_date(val: str | None) -> date | None:
    """날짜 문자열 파싱 (YYYY-MM-DD, YYYY.MM.DD, YYYYMMDD 등)."""
    if not val:
        return None
    val = str(val).strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(val, fmt).date()
        except Exception:  # noqa: BLE001 - EUM 단말기 데이터 읽기전용 조회/파싱 — API 응답 파싱 실패 시 빈 리스트/None으로 안전 폴백, 데이터 조회만 하고 쓰기 없음
            pass
    return None


def analyze(devices: list[dict]) -> dict:
    """단말기 목록 분석.

    Returns:
        dict{
            total: int,
            comm_disconnected: list,   # 통신단절
            long_installed: list,      # 장기 설치 (미사용 가능성)
            demolition_soon: list,     # 준공 임박 (철거일 30일 이내)
            normal: list,              # 정상 운용
            summary: str
        }
    """
    today = date.today()
    comm_disconnected = []
    long_installed = []
    demolition_soon = []
    normal = []

    for dev in devices:
        # 통신단절 판단 (통신상태 필드)
        comm_state = str(dev.get("통신상태", "")).strip()
        if comm_state and comm_state not in ("정상", "온라인", "연결", ""):
            comm_disconnected.append(
                {
                    "고유번호": dev.get("고유번호", ""),
                    "단말기번호": dev.get("단말기번호", ""),
                    "공사명": dev.get("공사명", ""),
                    "통신상태": comm_state,
                    "설치일": dev.get("설치일", ""),
                    "관할지사": dev.get("관할지사", ""),
                }
            )
            continue

        # 철거일 임박 판단
        demolition_str = dev.get("철거일", "") or dev.get("철거예정일", "")
        demolition_date = _parse_date(demolition_str)
        if demolition_date:
            days_left = (demolition_date - today).days
            if days_left <= DEMOLITION_WARNING_DAYS:
                demolition_soon.append(
                    {
                        "고유번호": dev.get("고유번호", ""),
                        "단말기번호": dev.get("단말기번호", ""),
                        "공사명": dev.get("공사명", ""),
                        "철거일": demolition_str,
                        "남은일수": days_left,
                        "관할지사": dev.get("관할지사", ""),
                    }
                )
                continue

        # 장기 설치 판단 (설치일수)
        days_raw = dev.get("설치일수", "") or dev.get("설치일수(일)", "")
        installed_days = _parse_days(days_raw)
        if installed_days is not None and installed_days >= UNUSED_THRESHOLD_DAYS:
            long_installed.append(
                {
                    "고유번호": dev.get("고유번호", ""),
                    "단말기번호": dev.get("단말기번호", ""),
                    "공사명": dev.get("공사명", ""),
                    "설치일수": installed_days,
                    "설치일": dev.get("설치일", ""),
                    "관할지사": dev.get("관할지사", ""),
                    "운용상태": dev.get("운용상태", ""),
                }
            )
            continue

        normal.append(dev)

    summary_lines = [
        f"전체 단말기: {len(devices)}대",
        f"  통신단절: {len(comm_disconnected)}대",
        f"  장기설치({UNUSED_THRESHOLD_DAYS}일 이상): {len(long_installed)}대",
        f"  준공임박({DEMOLITION_WARNING_DAYS}일 이내): {len(demolition_soon)}대",
        f"  정상 운용: {len(normal)}대",
    ]

    return {
        "total": len(devices),
        "comm_disconnected": comm_disconnected,
        "long_installed": long_installed,
        "demolition_soon": demolition_soon,
        "normal": normal,
        "summary": "\n".join(summary_lines),
    }


def main() -> dict:
    """모니터링 실행 및 결과 출력."""
    with op_context("eum_monitor") as ctx:
        devices = _load_devices()
        if not devices:
            print("단말기 데이터가 없습니다.")
            print("먼저 실행: python scripts/eum/extract_all_devices.py")
            ctx.set_result(msg="데이터 없음", ok=False)
            return {}

        result = analyze(devices)
        ctx.set_result(
            msg="모니터링 완료",
            total=result["total"],
            disconnected=len(result["comm_disconnected"]),
            long=len(result["long_installed"]),
            soon=len(result["demolition_soon"]),
        )

    print("=" * 60)
    print("EUM 단말기 운용 모니터링")
    print(f"기준일: {date.today().isoformat()}")
    print("=" * 60)
    print(result["summary"])

    if result["comm_disconnected"]:
        print(f"\n[통신단절 {len(result['comm_disconnected'])}대]")
        for d in result["comm_disconnected"]:
            print(f"  • {d['공사명']} | {d['단말기번호']} | 상태: {d['통신상태']} | {d['관할지사']}")

    if result["demolition_soon"]:
        print(f"\n[준공 임박 {len(result['demolition_soon'])}대 — {DEMOLITION_WARNING_DAYS}일 이내]")
        for d in result["demolition_soon"]:
            print(f"  • {d['공사명']} | {d['단말기번호']} | 철거일: {d['철거일']} (D-{d['남은일수']})")

    if result["long_installed"]:
        print(f"\n[장기 설치 {len(result['long_installed'])}대 — {UNUSED_THRESHOLD_DAYS}일 이상]")
        for d in result["long_installed"]:
            print(f"  • {d['공사명']} | {d['단말기번호']} | 설치일수: {d['설치일수']}일 | {d['관할지사']}")

    print("=" * 60)
    return result


if __name__ == "__main__":
    main()
