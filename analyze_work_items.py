"""사이트 스냅샷에서 할당된 업무 분석."""

import json
from datetime import datetime
from pathlib import Path

SITEMAP_DIR = Path("data/sitemap")


def analyze_work_items():
    """스냅샷에서 업무 항목 추출."""
    print("\n[할당된 업무 분석]\n")

    # 모든 스냅샷 파일 로드
    snapshots = {}
    for snapshot_file in SITEMAP_DIR.glob("eum.cw.or.kr_*.json"):
        try:
            with snapshot_file.open(encoding="utf-8") as f:
                data = json.load(f)
                page_title = data.get("title", "")
                url = data.get("url", "")

                # 파일명에서 페이지 타입 추출
                filename = snapshot_file.stem

                snapshots[filename] = {
                    "url": url,
                    "title": page_title,
                    "file": str(snapshot_file.name),
                    "buttons": [],
                }

                # 버튼 추출
                if data.get("frames"):
                    for frame in data["frames"]:
                        for button in frame.get("buttons", []):
                            text = button.get("text", "").strip()
                            if text and len(text) > 0:
                                snapshots[filename]["buttons"].append(text)
        except Exception as e:  # noqa: BLE001 - 스냅샷 JSON 파일 로드 실패를 화면에 출력만 하고 계속 진행 - 읽기전용 분석 스크립트, 실패한 스냅샷은 집계에서 제외될 뿐 위험 조작 없음
            print(f"  ✗ {snapshot_file.name} 로드 실패: {e}")

    # 업무 분석
    work_items = {
        "device_management": [],  # 단말기 관리 관련
        "reports": [],  # 보고 관련
        "approvals": [],  # 승인 관련
        "submissions": [],  # 제출 관련
        "inquiries": [],  # 조회 관련
    }

    keywords = {
        "device_management": ["단말기", "설치", "이력"],
        "reports": ["보고", "상황", "현황"],
        "approvals": ["승인", "검토", "결재"],
        "submissions": ["제출", "신청", "등록"],
        "inquiries": ["조회", "확인", "내역"],
    }

    for filename, snapshot_data in sorted(snapshots.items()):
        for button_text in snapshot_data["buttons"]:
            for category, kw_list in keywords.items():
                if any(kw in button_text for kw in kw_list):
                    work_items[category].append(
                        {
                            "text": button_text,
                            "page": snapshot_data["title"],
                            "url": snapshot_data["url"],
                            "snapshot": snapshot_data["file"],
                        }
                    )

    # 결과 출력
    print("[발견된 업무 항목]")
    print(f"스냅샷 분석: {len(snapshots)}개 파일")
    print(f"버튼 수: {sum(len(s['buttons']) for s in snapshots.values())}개\n")

    total_work = 0
    for category, items in work_items.items():
        if items:
            print(f"\n[{category.upper()}] - {len(items)}개")
            # 중복 제거 및 정렬
            unique_items = {}
            for item in items:
                if item["text"] not in unique_items:
                    unique_items[item["text"]] = item

            for text, item in sorted(unique_items.items()):
                print(f"  • {text}")
                print(f"    페이지: {item['page']}")
                total_work += 1

    # 요약 정보 저장
    work_summary = {
        "site": "eum.cw.or.kr",
        "site_name": "건설근로자공제회",
        "analysis_date": datetime.now().isoformat(),
        "snapshots_analyzed": len(snapshots),
        "work_categories": {
            "device_management": len(set(i["text"] for i in work_items["device_management"])),
            "reports": len(set(i["text"] for i in work_items["reports"])),
            "approvals": len(set(i["text"] for i in work_items["approvals"])),
            "submissions": len(set(i["text"] for i in work_items["submissions"])),
            "inquiries": len(set(i["text"] for i in work_items["inquiries"])),
        },
        "total_unique_work_items": total_work,
        "work_items_by_category": {
            cat: [{"text": item["text"], "page": item["page"]} for item in {i["text"]: i for i in items}.values()]
            for cat, items in work_items.items()
            if items
        },
    }

    # 저장
    output_file = SITEMAP_DIR / "eum_work_analysis.json"
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(work_summary, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 업무 분석 결과 저장: {output_file}")
    print(f"  총 발견된 업무 항목: {total_work}개")


if __name__ == "__main__":
    analyze_work_items()
