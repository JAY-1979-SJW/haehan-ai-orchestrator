"""EUM 공사업체 담당자 이메일 조회 (WEBMAN380M00)

단말기 현황 데이터에서 공사업체 이메일이 없는 경우
EUM WEBMAN380M00 또는 WEBMAN370M00에서 공사번호로 담당자 연락처 조회.

결과: data/eum_contact_map.json  {공사번호: {담당자, 연락처, 이메일}}
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.logger import get_logger

_log = get_logger(__name__)


def lookup_contacts_from_new_sites() -> dict:
    """WEBMAN370M00 (설치안내대상) 데이터에서 공사번호→연락처 맵 구축"""
    f = ROOT / "data" / "eum_new_sites_install_targets.json"
    if not f.exists():
        return {}

    data = json.loads(f.read_text(encoding="utf-8"))
    contact_map = {}
    for p in data.get("projects", []):
        num = p.get("공사번호", "").strip()
        email = p.get("이메일", "").strip()
        if num and email:
            contact_map[num] = {
                "담당자": p.get("담당자", ""),
                "연락처": p.get("연락처", ""),
                "이메일": email,
                "업체명": p.get("업체명", ""),
            }
    return contact_map


def enrich_devices_with_contacts(devices: list[dict], contact_map: dict) -> list[dict]:
    """단말기 데이터에 연락처 정보 추가"""
    enriched = []
    for d in devices:
        num = d.get("공사번호", "").strip()
        contact = contact_map.get(num, {})
        enriched.append({
            **d,
            "_담당자": contact.get("담당자", ""),
            "_연락처": contact.get("연락처", ""),
            "_이메일": contact.get("이메일", ""),
        })
    return enriched


def main():
    print("\n[EUM 공사업체 연락처 매핑]")

    # 신규 현장 데이터에서 맵 구축
    contact_map = lookup_contacts_from_new_sites()
    print(f"  신규 현장 데이터에서 {len(contact_map)}개 연락처 확보")

    # 단말기 데이터 로드
    df = ROOT / "data" / "eum_all_devices_complete.json"
    if not df.exists():
        print("  단말기 데이터 없음")
        return

    devices = json.loads(df.read_text(encoding="utf-8")).get("all_devices", [])
    enriched = enrich_devices_with_contacts(devices, contact_map)

    matched = [d for d in enriched if d.get("_이메일")]
    print(f"  단말기 {len(devices)}대 중 이메일 매핑: {len(matched)}대")

    for d in enriched:
        email = d.get("_이메일", "")
        mark = "✅" if email else "❌"
        print(f"  {mark} NO.{d['NO']} | {d['공사명'][:35]} | {email or '이메일없음'}")

    # 저장
    out = ROOT / "data" / "eum_contact_map.json"
    out.write_text(json.dumps(contact_map, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  ✓ 저장: {out.name}")

    # 단말기별 연락처 보강 결과도 저장
    enriched_out = ROOT / "data" / "eum_devices_with_contacts.json"
    enriched_out.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ 저장: {enriched_out.name}")


if __name__ == "__main__":
    main()
