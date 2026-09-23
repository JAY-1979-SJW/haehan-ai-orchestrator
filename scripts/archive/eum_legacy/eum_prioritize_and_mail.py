"""신규 현장 우선순위 선정 + 홍보 메일 초안 생성

[설치 기준 근거 - 건설근로자의 고용개선 등에 관한 법률]
  의무: 공공 1억 이상 / 민간 50억 이상
  자율: 3억 미만 소규모 (모바일 앱 대체 가능)

[우선순위 점수 기준]
  A. 공사 잔여기간 점수  (긴 공사 = 임대 수익 높음)
     - 잔여 12개월 이상: +40점
     - 잔여 6~12개월:   +25점
     - 잔여 6개월 미만: +10점

  B. 설치 긴급도 점수  (설치예정일 경과 = 즉시 연락 필요)
     - 설치예정일 이미 지남: +30점 (지금 당장 필요)
     - 30일 이내 설치예정:   +20점
     - 30~90일 이내:         +10점
     - 90일 초과:             +5점

  C. 등록 신선도 점수  (최근 등록 = 아직 다른 업체 접촉 전)
     - 30일 이내 등록: +20점
     - 60일 이내 등록: +10점
     - 90일 이내 등록: +5점

  D. 지역 접근성 점수  (해한소방 주 활동권)
     - 수도권(경기/서울/인천/의정부/서울남부): +10점
     - 기타: +0점

  총점 100점 기준 → S/A/B/C 등급 분류
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TODAY = date.today()

# 수도권 관할지사
METRO = {"경기", "서울", "인천", "의정부", "서울남부"}


def score_project(p: dict) -> dict:
    score = 0
    detail = []

    # A. 공사 잔여기간
    end_str = p.get("공사종료일", "")
    remaining_months = 0
    if end_str and len(end_str) >= 10:
        try:
            end_date = date.fromisoformat(end_str[:10])
            remaining_months = max(0, (end_date - TODAY).days // 30)
            if remaining_months >= 12:
                score += 40
                detail.append(f"잔여{remaining_months}개월(+40)")
            elif remaining_months >= 6:
                score += 25
                detail.append(f"잔여{remaining_months}개월(+25)")
            else:
                score += 10
                detail.append(f"잔여{remaining_months}개월(+10)")
        except:  # noqa: E722
            pass

    # B. 설치 긴급도
    inst_str = p.get("설치예정일", "")
    days_to_install = None
    if inst_str and len(inst_str) >= 10:
        try:
            inst_date = date.fromisoformat(inst_str[:10])
            days_to_install = (inst_date - TODAY).days
            if days_to_install < 0:
                score += 30
                detail.append(f"설치일경과{abs(days_to_install)}일전(+30)")
            elif days_to_install <= 30:
                score += 20
                detail.append(f"설치{days_to_install}일후(+20)")
            elif days_to_install <= 90:
                score += 10
                detail.append(f"설치{days_to_install}일후(+10)")
            else:
                score += 5
                detail.append(f"설치{days_to_install}일후(+5)")
        except:  # noqa: E722
            pass

    # C. 등록 신선도
    reg_str = p.get("등록일", "")
    if reg_str and len(reg_str) >= 10:
        try:
            reg_date = date.fromisoformat(reg_str[:10])
            days_since = (TODAY - reg_date).days
            if days_since <= 30:
                score += 20
                detail.append(f"등록{days_since}일전(+20)")
            elif days_since <= 60:
                score += 10
                detail.append(f"등록{days_since}일전(+10)")
            elif days_since <= 90:
                score += 5
                detail.append(f"등록{days_since}일전(+5)")
        except:  # noqa: E722
            pass

    # D. 지역 접근성
    jisa = p.get("관할지사", "").strip()
    if jisa in METRO:
        score += 10
        detail.append("수도권(+10)")

    # 등급 분류
    if score >= 80:
        grade = "S"
    elif score >= 60:
        grade = "A"
    elif score >= 40:
        grade = "B"
    else:
        grade = "C"

    return {
        **p,
        "_score": score,
        "_grade": grade,
        "_detail": ", ".join(detail),
        "_remaining_months": remaining_months,
        "_days_to_install": days_to_install,
    }


def make_mail(p: dict) -> str:
    company = p.get("업체명", "")  # noqa: F841
    manager = p.get("담당자", "담당자")
    project = p.get("공사명", "")
    addr = p.get("현장주소", "")
    inst_date = p.get("설치예정일", "")
    end_date = p.get("공사종료일", "")
    email = p.get("이메일", "")

    urgency = ""
    if p.get("_days_to_install") is not None:
        if p["_days_to_install"] < 0:
            urgency = f"\n※ 단말기 설치 예정일({inst_date})이 이미 경과하였습니다. 조속한 설치를 권고드립니다.\n"
        elif p["_days_to_install"] <= 30:
            urgency = f"\n※ 단말기 설치 예정일({inst_date})까지 {p['_days_to_install']}일 남았습니다.\n"

    return f"""수신: {email}
발신: 해한소방 단말기사업팀 (skyjwshin@gmail.com)
제목: [건설근로자 전자카드 단말기 임대 안내] {project}

{manager}님 안녕하세요.

해한소방 단말기사업팀입니다.

귀사가 시공 중인 현장 관련하여 건설근로자 전자카드 단말기 임대 서비스를 안내드립니다.

■ 현장 정보
  - 공사명: {project}
  - 현장주소: {addr}
  - 공사기간: ~ {end_date}
{urgency}
■ 건설근로자 전자카드 단말기 설치 의무 안내

2024년 1월부터 「건설근로자의 고용개선 등에 관한 법률」에 따라
  · 공공공사 1억원 이상
  · 민간공사 50억원 이상
해당 현장은 전자카드 단말기 설치가 의무입니다.

미설치 시 과태료 부과 대상이 될 수 있습니다.

■ 해한소방 단말기 임대 서비스

해한소방은 건설근로자공제회 지정 단말기 유통·임대 업체입니다.
현재 22개 현장에 단말기를 공급 중이며, 즉시 설치 가능한 재고를 보유하고 있습니다.

  ▶ 서비스 특징
    • 이동형 / 벽부형 선택 가능 (현장 맞춤)
    • EUM 등록부터 철거까지 일괄 처리
    • 신속한 A/S 지원
    • 합리적인 임대료

  ▶ 임대 절차 (간단 3단계)
    1. 문의 → 2. EUM 등록 → 3. 현장 설치 (최단 3일 내)

■ 연락처
  담당: 해한소방 단말기사업팀
  이메일: skyjwshin@gmail.com

설치 문의 또는 견적 요청은 언제든지 연락 주십시오.
감사합니다.

해한소방 단말기사업팀 드림
────────────────────────────────────────
"""


def main():
    f = ROOT / "data" / "eum_new_sites_install_targets.json"
    if not f.exists():
        print("데이터 없음. eum_extract_new_sites.py 먼저 실행 필요.")
        sys.exit(1)

    projects = json.loads(f.read_text(encoding="utf-8"))["projects"]
    print(f"\n{'=' * 80}")
    print(f"  신규 현장 우선순위 선정 | 기준일: {TODAY}")
    print(f"{'=' * 80}\n")

    # 점수 계산 + 중복 제거 (이메일+공사명 기준)
    scored_all = [score_project(p) for p in projects]
    seen = set()
    scored = []
    for p in scored_all:
        key = p["이메일"] + p["공사명"]
        if key not in seen:
            seen.add(key)
            scored.append(p)
    scored.sort(key=lambda x: x["_score"], reverse=True)
    print(f"중복 제거: {len(scored_all)}개 → {len(scored)}개")

    # 등급별 분류
    by_grade = {"S": [], "A": [], "B": [], "C": []}
    for p in scored:
        by_grade[p["_grade"]].append(p)

    print("[우선순위 기준]")
    print("  A. 공사 잔여기간: 12개월↑=+40 / 6~12개월=+25 / 6개월↓=+10")
    print("  B. 설치 긴급도 : 예정일경과=+30 / 30일이내=+20 / 90일이내=+10 / 그외=+5")
    print("  C. 등록 신선도 : 30일이내=+20 / 60일이내=+10 / 90일이내=+5")
    print("  D. 수도권 지역 : +10 (경기/서울/인천/의정부/서울남부)")
    print()
    print("[등급 분포]")
    for g in ["S", "A", "B", "C"]:
        print(f"  {g}등급: {len(by_grade[g]):3}개")
    print()

    # S/A등급 상세
    top = by_grade["S"] + by_grade["A"]
    print(f"{'=' * 80}")
    print(f"[S/A등급 우선 발송 대상] {len(top)}개")
    print(f"{'=' * 80}")

    for i, p in enumerate(top[:30], 1):
        print(f"\n  [{i:2}] {p['_grade']}등급 {p['_score']}점 | {p['공사명'][:45]}")
        print(f"       업체: {p['업체명']} | 관할: {p['관할지사']}")
        print(f"       설치예정: {p['설치예정일']} | 종료: {p['공사종료일']} | {p['_detail']}")
        print(f"       이메일: {p['이메일']}")

    if len(top) > 30:
        print(f"\n  ... 외 {len(top) - 30}개")

    # 결과 저장
    out_json = ROOT / "data" / f"eum_priority_sites_{TODAY.strftime('%Y%m%d')}.json"
    out_json.write_text(
        json.dumps(
            {
                "기준일": TODAY.isoformat(),
                "법적근거": {
                    "의무대상": "공공 1억원 이상 / 민간 50억원 이상 (건설근로자법 2024.01 기준)",
                    "자율대상": "3억원 미만 소규모 (모바일앱 대체 가능)",
                },
                "점수기준": {
                    "A_잔여기간": "12개월↑=40 / 6~12개월=25 / 6개월↓=10",
                    "B_설치긴급도": "경과=30 / 30일이내=20 / 90일이내=10 / 그외=5",
                    "C_등록신선도": "30일이내=20 / 60일이내=10 / 90일이내=5",
                    "D_수도권": "경기/서울/인천/의정부/서울남부=10",
                },
                "등급분포": {g: len(lst) for g, lst in by_grade.items()},
                "S등급": [
                    {
                        "NO": p["NO"],
                        "공사명": p["공사명"],
                        "업체명": p["업체명"],
                        "이메일": p["이메일"],
                        "점수": p["_score"],
                        "근거": p["_detail"],
                    }
                    for p in by_grade["S"]
                ],
                "A등급": [
                    {
                        "NO": p["NO"],
                        "공사명": p["공사명"],
                        "업체명": p["업체명"],
                        "이메일": p["이메일"],
                        "점수": p["_score"],
                        "근거": p["_detail"],
                    }
                    for p in by_grade["A"]
                ],
                "전체_점수순": scored,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # 메일 초안 저장 (S/A등급만)
    out_mail = ROOT / "data" / f"promo_mails_priority_{TODAY.strftime('%Y%m%d')}.txt"
    with open(out_mail, "w", encoding="utf-8") as mf:
        mf.write("# 단말기 임대 홍보 메일 - S/A등급 우선 발송\n")
        mf.write(f"# 생성일: {TODAY} | 대상: {len(top)}개 현장\n\n")
        mf.write("=" * 80 + "\n")
        mf.write("[우선순위 기준 요약]\n")
        mf.write("  공사 잔여기간 + 설치 긴급도 + 등록 신선도 + 수도권 여부\n")
        mf.write("  법적근거: 공공 1억원 이상 / 민간 50억원 이상 의무설치\n")
        mf.write("=" * 80 + "\n\n")

        for i, p in enumerate(top, 1):
            mf.write(f"{'─' * 60}\n")
            mf.write(f"[{i}/{len(top)}] {p['_grade']}등급 {p['_score']}점 | {p['공사명']}\n")
            mf.write(f"우선순위 근거: {p['_detail']}\n\n")
            mf.write(make_mail(p))
            mf.write("\n")

    print(f"\n{'=' * 80}")
    print(f"✓ 우선순위 JSON: {out_json.name}")
    print(f"✓ 메일 초안 TXT: {out_mail.name}")
    print(f"  → S/A등급 {len(top)}개 메일 작성 완료")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
