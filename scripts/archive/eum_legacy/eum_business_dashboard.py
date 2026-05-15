"""해한소방 단말기 임대 업무 종합 대시보드

업무 파이프라인:
  신규문의 → 계약 → EUM등록/설치 → 운용중 → 준공/종료신청 → 단말기회수 → 정산/서류종료

주요 자동화:
  1. 전체 임대 현황 추출 (WEBMAN390M00)
  2. 통신 단절 / 미사용 단말기 경고
  3. 신규 홍보 대상 현장 탐색 (WEBMAN380M00 미등록 공사)
  4. 홍보 메일 초안 생성
"""
from __future__ import annotations

import json
import sys
import time
import re
from pathlib import Path
from datetime import datetime, date

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.logger import get_logger

_log = get_logger(__name__)

TODAY = date.today()


# ── 데이터 로드 ─────────────────────────────────────────────────────────────

def load_device_data() -> list[dict]:
    f = ROOT / "data" / "eum_all_devices_complete.json"
    if not f.exists():
        _log.warning("단말기 데이터 없음 - eum_extract_all_devices.py 먼저 실행 필요")
        return []
    d = json.loads(f.read_text(encoding='utf-8'))
    return d.get("all_devices", [])


# ── 업무 분석 ─────────────────────────────────────────────────────────────────

def analyze_devices(devices: list[dict]) -> dict:
    """단말기 상태 전수 분석"""

    result = {
        "total": len(devices),
        "임대중": [],
        "통신단절_주의": [],    # 단절일 30일 이상
        "통신단절_심각": [],    # 단절일 100일 이상
        "미사용_의심": [],      # 처리건수 0 + 설치일수 30일 이상
        "장기설치": [],         # 설치일수 700일 이상
        "신규설치": [],         # 설치일수 60일 이하
        "by_지사": {},
        "by_단말기유형": {},
    }

    for d in devices:
        result["임대중"].append(d)

        # 통신 단절 파싱
        comm = d.get("통신상태", "")
        days_cut = 0
        m = re.search(r"\((\d+)\)", comm)
        if m and "단절" in comm:
            days_cut = int(m.group(1))

        if days_cut >= 100:
            result["통신단절_심각"].append({**d, "_단절일수": days_cut})
        elif days_cut >= 30:
            result["통신단절_주의"].append({**d, "_단절일수": days_cut})

        # 미사용 의심
        cnt = d.get("처리건수", "0").replace(",", "")
        inst_days = int(d.get("설치일수", "0") or "0")
        if cnt == "0" and inst_days >= 30:
            result["미사용_의심"].append(d)

        # 장기설치
        if inst_days >= 700:
            result["장기설치"].append({**d, "_설치일수": inst_days})

        # 신규설치
        if inst_days <= 60:
            result["신규설치"].append({**d, "_설치일수": inst_days})

        # 관할지사별
        jisa = d.get("관할지사", "미분류")
        result["by_지사"].setdefault(jisa, []).append(d)

        # 단말기유형별
        typ = d.get("단말기유형", "미분류")
        result["by_단말기유형"].setdefault(typ, 0)
        result["by_단말기유형"][typ] += 1

    return result


# ── 미처리 업무 목록 ────────────────────────────────────────────────────────

def build_pending_tasks(analysis: dict) -> list[dict]:
    """미처리/주의 업무 목록 생성"""
    tasks = []

    for d in sorted(analysis["통신단절_심각"], key=lambda x: x["_단절일수"], reverse=True):
        tasks.append({
            "우선순위": "🔴 긴급",
            "유형": "통신단절(심각)",
            "NO": d["NO"],
            "공사명": d["공사명"],
            "공사업체": d["공사업체"],
            "단절일수": d["_단절일수"],
            "관할지사": d["관할지사"],
            "조치": f"현장 방문 또는 공사업체({d['공사업체']}) 연락하여 단말기 상태 확인"
        })

    for d in sorted(analysis["통신단절_주의"], key=lambda x: x["_단절일수"], reverse=True):
        tasks.append({
            "우선순위": "🟡 주의",
            "유형": "통신단절(주의)",
            "NO": d["NO"],
            "공사명": d["공사명"],
            "공사업체": d["공사업체"],
            "단절일수": d["_단절일수"],
            "관할지사": d["관할지사"],
            "조치": "공사업체 연락하여 단말기 사용 여부 확인"
        })

    for d in analysis["미사용_의심"]:
        tasks.append({
            "우선순위": "🟡 주의",
            "유형": "미사용의심(처리건수0)",
            "NO": d["NO"],
            "공사명": d["공사명"],
            "공사업체": d["공사업체"],
            "단절일수": "-",
            "관할지사": d["관할지사"],
            "조치": f"설치 {d['설치일수']}일 경과, 처리건수 0 - 근로자 전자카드 사용 여부 확인"
        })

    for d in analysis["장기설치"]:
        tasks.append({
            "우선순위": "🟢 참고",
            "유형": "장기설치(공사종료검토)",
            "NO": d["NO"],
            "공사명": d["공사명"],
            "공사업체": d["공사업체"],
            "단절일수": "-",
            "관할지사": d["관할지사"],
            "조치": f"설치 {d['_설치일수']}일 - 공사 준공 여부 및 단말기 회수 필요성 확인"
        })

    return tasks


# ── 홍보 메일 초안 ──────────────────────────────────────────────────────────

def generate_promo_email(device: dict) -> str:
    """신규/장기 공사 현장 홍보 메일 초안"""
    company = device.get("공사업체", "")
    project = device.get("공사명", "")
    issuer = device.get("발주기관", "")
    jisa = device.get("관할지사", "")

    return f"""
수신: {company} 담당자님
발신: 해한소방 단말기사업팀
제목: 건설근로자 전자카드 단말기 임대 서비스 안내 - {project}

안녕하세요, 해한소방 단말기사업팀입니다.

귀사가 시공 중인 [{project}] 현장의 건설근로자 전자카드 단말기 관련 안내를 드립니다.

▶ 건설근로자 전자카드 단말기 임대 서비스

해한소방은 건설근로자공제회(EUM) 공식 단말기 유통업체로서, 현장 맞춤형 단말기 임대 서비스를 제공합니다.

[서비스 특징]
  • 즉시 설치 가능 (재고 보유 중)
  • 이동형 / 벽부형 / 부스형 / 게이트형 선택 가능
  • 설치부터 철거까지 일괄 관리
  • 고장 시 신속 A/S 지원

[임대 절차]
  1. 문의 및 견적 → 2. 계약 체결 → 3. EUM 등록 → 4. 현장 설치 → 5. 운용
  → 6. 공사 준공 시 철거 신청 → 7. 단말기 회수 및 계약 종료

[연락처]
  • 담당: 해한소방 단말기사업팀
  • 전화:
  • 이메일: skyjwshin@gmail.com

건설근로자공제회 의무 대상 현장은 전자카드 단말기 설치가 필수입니다.
임대 문의 주시면 즉시 지원해 드리겠습니다.

감사합니다.
해한소방 드림
"""


# ── 전체 파이프라인 출력 ────────────────────────────────────────────────────

PIPELINE = """
┌─────────────────────────────────────────────────────────────────────────────┐
│          단말기 임대 전체 업무 파이프라인 (해한소방)                          │
└─────────────────────────────────────────────────────────────────────────────┘

[1단계] 신규 현장 발굴/홍보
  - EUM WEBMAN380M00에서 신규 승인 공사 목록 조회
  - 단말기 미설치 현장 파악
  - 공사업체에 홍보 메일 발송 → 계약 체결

[2단계] 계약 및 EUM 등록
  - 임대 계약서 작성 (공사업체 ↔ 해한소방)
  - EUM 사이트에서 단말기 설치 신청 등록
  - 건설근로자공제회 승인 확인

[3단계] 단말기 설치
  - 현장 방문 및 단말기 설치 (이동형/벽부형 등)
  - EUM에서 설치일 등록
  - 단말기 정상 통신 확인

[4단계] 운용 모니터링 (진행 중 - 현재 22개 현장)
  - 주 1회 EUM WEBMAN390M00에서 현황 추출
  - 통신 단절 단말기 확인 및 조치
  - 처리건수 이상 현장 확인
  - 공사업체 소통

[5단계] 공사 준공/임대 종료
  - 공사업체로부터 준공 통보 접수
  - EUM에서 철거일 등록 신청
  - 단말기 현장 회수

[6단계] 정산 및 서류 종료
  - 임대료 정산 (설치일수 기준)
  - EUM 철거 완료 처리
  - 임대 계약 종료 서류 처리
  - 단말기 재고 복귀 및 상태 점검

────────────────────────────────────────────────────────────────────────────
현재 자동화 현황:
  ✅ 4단계: eum_extract_all_devices.py (주 1회 실행)
  ✅ 1단계: eum_business_dashboard.py (홍보 대상 메일 초안)
  ⬜ 2단계: EUM 등록은 수동 (접근 제한)
  ⬜ 5/6단계: 종료/정산은 수동
"""


# ── 메인 ────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "="*80)
    print("  해한소방 단말기 임대 업무 종합 대시보드")
    print(f"  기준일: {TODAY}")
    print("="*80)

    # 데이터 로드
    devices = load_device_data()
    if not devices:
        print("\n⚠️ 단말기 데이터 없음. scripts/eum_extract_all_devices.py 먼저 실행하세요.")
        sys.exit(1)

    # 분석
    analysis = analyze_devices(devices)

    # 1. 파이프라인
    print(PIPELINE)

    # 2. 현황 요약
    print("="*80)
    print("[현재 임대 현황 요약]")
    print("="*80)
    print(f"  총 임대 단말기: {analysis['total']}대")
    print(f"  통신 정상:      {analysis['total'] - len(analysis['통신단절_심각']) - len(analysis['통신단절_주의'])}대")
    print(f"  통신단절 심각:  {len(analysis['통신단절_심각'])}대 (100일 이상)")
    print(f"  통신단절 주의:  {len(analysis['통신단절_주의'])}대 (30~99일)")
    print(f"  미사용 의심:    {len(analysis['미사용_의심'])}대 (처리건수 0)")
    print(f"  장기설치:       {len(analysis['장기설치'])}대 (700일 이상, 준공 검토 필요)")
    print(f"  신규설치:       {len(analysis['신규설치'])}대 (60일 이하)")

    print(f"\n  [관할지사별]")
    for jisa, lst in sorted(analysis["by_지사"].items()):
        print(f"    {jisa:<15}: {len(lst)}대")

    print(f"\n  [단말기 유형별]")
    for typ, cnt in sorted(analysis["by_단말기유형"].items()):
        print(f"    {typ:<10}: {cnt}대")

    # 3. 미처리 업무 목록
    tasks = build_pending_tasks(analysis)
    print(f"\n{'='*80}")
    print(f"[미처리/주의 업무 목록] 총 {len(tasks)}건")
    print("="*80)

    for i, t in enumerate(tasks, 1):
        print(f"\n  [{i:2}] {t['우선순위']} [{t['유형']}]")
        print(f"       NO={t['NO']} | {t['공사명'][:40]}")
        print(f"       공사업체: {t['공사업체']} | 관할: {t['관할지사']}")
        if t['단절일수'] != '-':
            print(f"       단절일수: {t['단절일수']}일")
        print(f"       조치: {t['조치']}")

    # 4. 신규 홍보 대상 (신규설치 현장 = 새로 시작한 공사업체)
    print(f"\n{'='*80}")
    print(f"[홍보 메일 대상 - 신규 설치 현장 {len(analysis['신규설치'])}개]")
    print("="*80)
    print("  ※ 신규 설치 현장의 공사업체에 추가 단말기 또는 연장 계약 홍보 가능")

    promo_targets = []
    for d in analysis["신규설치"]:
        print(f"\n  NO={d['NO']} | {d['공사명'][:45]}")
        print(f"    공사업체: {d['공사업체']} | 설치일: {d['설치일']} | 설치일수: {d['_설치일수']}일")
        promo_targets.append(d)

    # 5. 홍보 메일 초안 저장
    mail_output = ROOT / "data" / f"promo_mails_{TODAY.strftime('%Y%m%d')}.txt"
    with open(mail_output, "w", encoding="utf-8") as f:
        f.write(f"# 단말기 임대 홍보 메일 초안\n생성일: {TODAY}\n\n")
        f.write("="*80 + "\n")
        f.write("【신규 현장 - 추가 단말기 홍보 대상】\n")
        f.write("="*80 + "\n\n")
        for d in promo_targets:
            f.write(f"{'─'*60}\n")
            f.write(f"수신: {d['공사업체']}\n")
            f.write(f"현장: {d['공사명']}\n\n")
            f.write(generate_promo_email(d))
            f.write("\n\n")

        f.write("="*80 + "\n")
        f.write("【장기설치 현장 - 준공 후 회수 안내 메일 대상】\n")
        f.write("="*80 + "\n\n")
        for d in analysis["장기설치"]:
            f.write(f"{'─'*60}\n")
            f.write(f"수신: {d['공사업체']}\n")
            f.write(f"현장: {d['공사명']} (설치 {d['_설치일수']}일)\n\n")
            f.write(f"제목: 단말기 임대 종료 및 회수 안내 - {d['공사명']}\n\n")
            f.write(f"안녕하세요, 해한소방 단말기사업팀입니다.\n\n")
            f.write(f"귀사 현장 [{d['공사명']}]에 설치된 건설근로자 전자카드 단말기 임대 기간 관련 안내입니다.\n\n")
            f.write(f"현재 설치 후 {d['_설치일수']}일이 경과하였습니다.\n")
            f.write(f"공사 준공 또는 임대 종료 시 EUM 철거 신청 및 단말기 반납 절차가 필요합니다.\n\n")
            f.write(f"준공 예정이시면 사전에 연락 주시어 원활한 절차를 진행할 수 있도록 부탁드립니다.\n\n")
            f.write(f"연락처: 해한소방 / skyjwshin@gmail.com\n\n")

    # 6. JSON 요약 저장
    summary_output = ROOT / "data" / f"business_dashboard_{TODAY.strftime('%Y%m%d')}.json"
    summary = {
        "기준일": TODAY.isoformat(),
        "총임대": analysis["total"],
        "통신단절_심각": [{"NO": d["NO"], "공사명": d["공사명"], "공사업체": d["공사업체"], "단절일수": d["_단절일수"]} for d in analysis["통신단절_심각"]],
        "통신단절_주의": [{"NO": d["NO"], "공사명": d["공사명"], "공사업체": d["공사업체"], "단절일수": d["_단절일수"]} for d in analysis["통신단절_주의"]],
        "미사용_의심": [{"NO": d["NO"], "공사명": d["공사명"], "공사업체": d["공사업체"]} for d in analysis["미사용_의심"]],
        "장기설치_준공검토": [{"NO": d["NO"], "공사명": d["공사명"], "공사업체": d["공사업체"], "설치일수": d["_설치일수"]} for d in analysis["장기설치"]],
        "신규설치_홍보대상": [{"NO": d["NO"], "공사명": d["공사명"], "공사업체": d["공사업체"], "설치일수": d["_설치일수"]} for d in analysis["신규설치"]],
        "미처리업무_총건수": len(tasks),
    }
    summary_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f"\n{'='*80}")
    print(f"✓ 대시보드 저장: {summary_output.name}")
    print(f"✓ 홍보 메일 초안: {mail_output.name}")
    print("="*80 + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log.error(f"실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
