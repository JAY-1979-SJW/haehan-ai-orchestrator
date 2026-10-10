"""건설근로자공제회 단말기 재고 관리 자동화
사이트 구조 + 탐색 결과 반영

핵심 로직:
1. WEBMAN390M00 페이지에서 40대 단말기 데이터 추출
2. HTML 정규식 기반 테이블 파싱 (DOM 추출은 실패)
3. 임대 상태 분류: rental_type이 '임대'이고 end_date 있으면 "서류정리필요"
4. 18개 임대 현장별 그룹화
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.browser.cdp.connection import get_page  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402

_log = get_logger(__name__)


class EumDeviceInventoryManager:
    """건설근로자공제회 단말기 재고 관리"""

    SITEMAP_FILE = ROOT / "data" / "sitemap" / "eum.cw.or.kr_complete_sitemap_v2.json"
    WEBMAN390_URL = "https://eum.cw.or.kr/web/man/WEBMAN390M00"

    def __init__(self):
        self.sitemap = self._load_sitemap()
        self.page = None
        self.devices = []

    def _load_sitemap(self) -> dict:
        """사이트맵 로드"""
        if self.SITEMAP_FILE.exists():
            with self.SITEMAP_FILE.open(encoding="utf-8") as f:
                return json.load(f)
        return {}

    def extract_devices_from_html(self, html_content: str) -> list:
        """HTML에서 테이블 데이터 추출 (정규식 기반)

        WEBMAN390M00에서 40대 단말기 데이터를 추출합니다.
        DOM 쿼리 대신 정규식 기반 파싱을 사용합니다.
        """
        # <tr><td>...</td>...</tr> 패턴 추출
        tr_pattern = r"<tr[^>]*>(.*?)</tr>"
        td_pattern = r"<td[^>]*>(.*?)</td>"

        matches = re.findall(tr_pattern, html_content, re.DOTALL)
        rows = []

        for match in matches:
            cells = re.findall(td_pattern, match, re.DOTALL)
            if not cells:
                continue

            # HTML 태그 제거 및 텍스트 정제
            cell_texts = []
            for cell in cells:
                # HTML 태그 제거
                text = re.sub(r"<[^>]+>", "", cell)
                # 공백 정제
                text = re.sub(r"\s+", " ", text).strip()

                if text and len(text) < 200:
                    cell_texts.append(text)

            # 최소 3개 이상 셀 필터링
            if len(cell_texts) >= 3:
                rows.append(cell_texts)

        return rows

    def parse_device_rows(self, raw_rows: list) -> list:
        """원본 행을 디바이스 객체로 변환"""
        devices = []

        for row in raw_rows:
            # 필터 옵션 제외
            # 특정 키워드가 포함된 경우 제외
            row_text = " ".join(row).lower()
            if any(keyword in row_text for keyword in ["선택", "전체", "당일", "당월", "전월", "해당없음"]):
                continue

            # 첫 셀이 숫자(NO)가 아니면 제외
            if not row[0].isdigit():
                continue

            # 디바이스 객체 생성
            device = {
                "no": row[0] if len(row) > 0 else "",
                "unique_id": row[1] if len(row) > 1 else "",
                "quantity": row[2] if len(row) > 2 else "1",
                "insurance_number": row[3] if len(row) > 3 else "",
                "project": row[4] if len(row) > 4 else "",
                "location": row[5] if len(row) > 5 else "",
                "type_flag": row[6] if len(row) > 6 else "",
                "manager": row[7] if len(row) > 7 else "",
                "device_type": row[8] if len(row) > 8 else "",
                "status": row[9] if len(row) > 9 else "",
                "end_date": row[10] if len(row) > 10 else "",
                "rental_type": row[12] if len(row) > 12 else "",
            }

            # 추가 로직: 임대 상태 분류
            device["rental_status"] = self._determine_rental_status(device)
            devices.append(device)

        return devices

    def _determine_rental_status(self, device: dict) -> str:
        """임대 상태 판단

        비즈니스 규칙:
        - rental_type = '임대'이고 end_date가 있으면 → "서류정리필요"
        - rental_type = '임대'이고 end_date 없으면 → "임대중"
        - rental_type != '임대' → "구매" 또는 기타
        """
        rental = device["rental_type"].strip()
        end_date = device["end_date"].strip()

        if rental == "임대":
            if end_date:
                return "서류정리필요"
            else:
                return "임대중"
        else:
            return "구매" if rental == "구매" else "기타"

    def fetch_and_extract(self) -> dict:
        """페이지에서 데이터 추출"""
        _log.info(f"[추출 시작] {self.WEBMAN390_URL}")

        self.page = get_page()

        try:
            # 페이지 접속
            self.page.goto(self.WEBMAN390_URL, timeout=30000)
            self.page.wait_for_load_state("load", timeout=5000)

            # 팝업 처리
            try:
                from scripts.browser.popup.popup_detector import handle_page_popups

                handle_page_popups(self.page, timeout_s=2.0)
            except:  # noqa: E722
                pass

            # HTML 추출
            html_content = self.page.content()

            # 테이블 데이터 추출
            raw_rows = self.extract_devices_from_html(html_content)
            _log.info(f"[파싱] 테이블 행: {len(raw_rows)}개")

            # 디바이스 객체로 변환
            self.devices = self.parse_device_rows(raw_rows)
            _log.info(f"[필터링] 유효한 단말기: {len(self.devices)}개")

            # 통계
            stats = self._calculate_statistics()

            return {
                "success": True,
                "devices": self.devices,
                "statistics": stats,
                "extraction_time": datetime.now().isoformat(),
            }

        except Exception as e:  # noqa: BLE001 - EUM 단말기 재고 자동화(구버전, archive 보존) -- 추출 실패를 로깅·트레이스백 출력 후 에러 결과 반환, 최상위 실행 실패 시 종료코드 1
            _log.error(f"추출 실패: {e}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def _calculate_statistics(self) -> dict:
        """통계 계산"""
        stats: dict[str, Any] = {
            "total_devices": len(self.devices),
            "rental_active": 0,
            "rental_pending_paperwork": 0,
            "purchased": 0,
            "by_location": {},
            "by_status": {},
        }

        for device in self.devices:
            rental_status = device["rental_status"]

            if rental_status == "임대중":
                stats["rental_active"] += 1
            elif rental_status == "서류정리필요":
                stats["rental_pending_paperwork"] += 1
            else:
                stats["purchased"] += 1

            # 위치별
            location = device["location"].split()[0] if device["location"] else "미분류"
            stats["by_location"][location] = stats["by_location"].get(location, 0) + 1

            # 상태별
            status = device["status"] or "미분류"
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

        return stats

    def group_by_location(self) -> dict:
        """현장별 그룹화"""
        grouped: dict[Any, Any] = {}

        for device in self.devices:
            location = device["location"].strip()

            if location not in grouped:
                grouped[location] = []

            grouped[location].append(
                {
                    "no": device["no"],
                    "project": device["project"],
                    "status": device["rental_status"],
                    "end_date": device["end_date"],
                    "device_type": device["device_type"],
                }
            )

        return grouped

    def generate_report(self, result: dict) -> str:
        """보고서 생성"""
        if not result["success"]:
            return "❌ 데이터 추출 실패"

        stats = result["statistics"]

        report = f"""
{"=" * 80}
📊 건설근로자공제회 단말기 재고 자동 보고서
{"=" * 80}
조회 시간: {result["extraction_time"]}

[총괄]
  • 총 단말기: {stats["total_devices"]}대
  • 임대 중: {stats["rental_active"]}대
  • 임대 종료 (서류정리필요): {stats["rental_pending_paperwork"]}대
  • 구매/기타: {stats["purchased"]}대

[현장별 분포]
"""
        grouped = self.group_by_location()
        for location in sorted(grouped.keys()):
            items = grouped[location]
            pending = sum(1 for i in items if i["status"] == "서류정리필요")
            active = sum(1 for i in items if i["status"] == "임대중")

            report += f"  {location:<20}: {len(items):2}대 (임대중:{active} 정리필요:{pending})\n"

        report += """
[상태별]
"""
        for status, count in sorted(stats["by_status"].items()):
            report += f"  • {status:<15}: {count:2}대\n"

        report += f"""
{"─" * 80}
⚠️ 주의사항
  • 임대 종료된 항목도 서류상 미종료로 표시되어 있음
  • 반납 및 정산 절차 필요한 항목: {stats["rental_pending_paperwork"]}대
  • 다음 확인: {(stats["rental_active"] + stats["rental_pending_paperwork"])}대

생성됨: 자동화 스크립트 (scripts/eum_device_inventory_automation.py)
{"=" * 80}
"""
        return report

    def save_report(self, result: dict) -> Path:
        """보고서 저장"""
        output_file = ROOT / "data" / f"device_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_data = {
            "timestamp": result["extraction_time"],
            "statistics": result.get("statistics", {}),
            "devices": result.get("devices", []),
            "grouped_by_location": self.group_by_location(),
        }

        output_file.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
        _log.info(f"✓ 보고서 저장: {output_file}")

        return output_file


def main():
    """메인 실행"""
    manager = EumDeviceInventoryManager()

    print("\n" + "=" * 80)
    print("🔄 건설근로자공제회 단말기 재고 자동 추출 시작")
    print("=" * 80)

    result = manager.fetch_and_extract()

    if result["success"]:
        # 보고서 출력
        report = manager.generate_report(result)
        print(report)

        # 보고서 저장
        manager.save_report(result)

    else:
        print(f"❌ 실패: {result.get('error')}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 - EUM 단말기 재고 자동화(구버전, archive 보존) -- 추출 실패를 로깅·트레이스백 출력 후 에러 결과 반환, 최상위 실행 실패 시 종료코드 1
        _log.error(f"실행 실패: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
