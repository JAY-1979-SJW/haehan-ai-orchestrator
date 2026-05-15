"""EUM 업무 자동화 통합 실행기

처리 가능 업무:
  1. 통신단절 단말기 → 공사업체 Gmail 알림 메일
  2. 미사용 단말기   → 공사업체 사용 안내 메일
  3. 신규 현장 S/A등급 → 홍보 메일 발송
  4. 고장신고내역 조회 (WEBMAN420M00)

실행 방식:
  python scripts/eum_task_runner.py [--dry-run] [--task {all|comm|unused|promo|fault}]

  --dry-run  : 메일 발송하지 않고 초안만 출력
  --task all : 모든 업무 순차 실행 (기본값)
  --task comm: 통신단절 알림만
  --task unused: 미사용 안내만
  --task promo : 홍보 메일만
  --task fault : 고장신고내역 조회만

각 메일 발송 전 사용자 승인 대기.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.logger import get_logger

_log = get_logger(__name__)
TODAY = date.today()

SENDER = "skyjwshin@gmail.com"
SENDER_NAME = "해한소방 단말기사업팀"


# ── 데이터 로드 ─────────────────────────────────────────────────────────────

def load_devices() -> list[dict]:
    f = ROOT / "data" / "eum_all_devices_complete.json"
    if not f.exists():
        print("⚠  단말기 데이터 없음 → scripts/eum_extract_all_devices.py 먼저 실행")
        sys.exit(1)
    return json.loads(f.read_text(encoding="utf-8")).get("all_devices", [])


def load_priority_sites() -> list[dict]:
    files = sorted((ROOT / "data").glob("eum_priority_sites_*.json"), reverse=True)
    if not files:
        print("⚠  우선순위 데이터 없음 → scripts/eum_prioritize_and_mail.py 먼저 실행")
        return []
    data = json.loads(files[0].read_text(encoding="utf-8"))
    sa = data.get("S등급", []) + data.get("A등급", [])
    return sa


# ── 분석 ────────────────────────────────────────────────────────────────────

def parse_cut_days(comm: str) -> int:
    m = re.search(r"\((\d+)\)", comm)
    if m and "단절" in comm:
        return int(m.group(1))
    return 0


def analyze(devices: list[dict]) -> dict:
    comm_critical, comm_warn, unused = [], [], []
    for d in devices:
        days = parse_cut_days(d.get("통신상태", ""))
        if days >= 100:
            comm_critical.append({**d, "_단절일수": days})
        elif days >= 30:
            comm_warn.append({**d, "_단절일수": days})

        cnt = d.get("처리건수", "0").replace(",", "")
        inst = int(d.get("설치일수", "0") or "0")
        if cnt == "0" and inst >= 30:
            unused.append(d)

    comm_critical.sort(key=lambda x: x["_단절일수"], reverse=True)
    comm_warn.sort(key=lambda x: x["_단절일수"], reverse=True)
    return {"comm_critical": comm_critical, "comm_warn": comm_warn, "unused": unused}


# ── 메일 본문 생성 ───────────────────────────────────────────────────────────

def mail_comm_alert(d: dict) -> dict:
    days = d["_단절일수"]
    level = "긴급" if days >= 100 else "주의"
    subject = f"[{level}] 건설근로자 전자카드 단말기 통신단절 확인 요청 - {d['공사명'][:30]}"
    body = f"""{d['공사업체']} 담당자님 안녕하세요.

해한소방 단말기사업팀입니다.

귀사 현장에 설치된 건설근로자 전자카드 단말기의 통신이 {days}일째 단절 상태입니다.

■ 현장 정보
  - 공사명: {d['공사명']}
  - 관할지사: {d['관할지사']}
  - 단말기 고유번호: {d['고유번호']}
  - 설치일: {d['설치일']} ({d['설치일수']}일 경과)
  - 통신 단절: {days}일

■ 조치 요청
  단말기 통신이 지속 단절될 경우 건설근로자의 출역 기록이 누락됩니다.
  현장 내 단말기 전원 및 통신 상태를 확인해 주시기 바랍니다.

  확인 후에도 단절이 지속되면 즉시 연락 주시면 기술 지원 드리겠습니다.

■ 연락처
  담당: 해한소방 단말기사업팀
  이메일: {SENDER}

감사합니다.
{SENDER_NAME} 드림"""
    return {"to": "", "subject": subject, "body": body, "device": d}


def mail_unused_notice(d: dict) -> dict:
    inst = int(d.get("설치일수", "0") or "0")
    subject = f"[안내] 건설근로자 전자카드 미사용 현장 확인 요청 - {d['공사명'][:30]}"
    body = f"""{d['공사업체']} 담당자님 안녕하세요.

해한소방 단말기사업팀입니다.

귀사 현장에 설치된 건설근로자 전자카드 단말기의 처리 실적이 없음을 확인하였습니다.

■ 현장 정보
  - 공사명: {d['공사명']}
  - 관할지사: {d['관할지사']}
  - 단말기 고유번호: {d['고유번호']}
  - 설치일: {d['설치일']} ({inst}일 경과)
  - 처리건수: 0건

■ 안내
  건설근로자 전자카드 단말기는 근로자가 출역 시 매일 태깅이 필요합니다.
  미사용 시 건설근로자법 위반으로 과태료 부과 대상이 될 수 있습니다.

  현장 관리자에게 단말기 사용 방법 안내를 부탁드립니다.
  사용 안내가 필요하시면 연락 주시기 바랍니다.

■ 연락처
  담당: 해한소방 단말기사업팀
  이메일: {SENDER}

감사합니다.
{SENDER_NAME} 드림"""
    return {"to": "", "subject": subject, "body": body, "device": d}


def mail_promo(p: dict) -> dict:
    subject = f"[건설근로자 전자카드 단말기 임대 안내] {p['공사명'][:40]}"
    body = f"""{p['업체명']} 담당자님 안녕하세요.

해한소방 단말기사업팀입니다.

귀사 현장의 건설근로자 전자카드 단말기 임대 서비스를 안내드립니다.

■ 현장 정보
  - 공사명: {p['공사명']}
  - 우선순위: {p.get('점수', '')}점 ({p.get('근거', '')})

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
  이메일: {SENDER}

설치 문의 또는 견적 요청은 언제든지 연락 주십시오.
감사합니다.

{SENDER_NAME} 드림"""
    return {"to": p.get("이메일", ""), "subject": subject, "body": body, "site": p}


# ── Gmail 발송 ───────────────────────────────────────────────────────────────

def send_gmail(to: str, subject: str, body: str) -> bool:
    """Gmail 브라우저 자동화로 메일 발송"""
    try:
        from scripts.google.gmail import _task_compose
        from scripts.web_connector import get_page
        page = get_page()
        _task_compose(page, [to, subject, body])
        return True
    except Exception as e:
        _log.error(f"Gmail 발송 실패: {e}")
        return False


# ── 사용자 승인 ──────────────────────────────────────────────────────────────

def confirm(prompt: str) -> bool:
    try:
        ans = input(f"\n{prompt} [y/N] ").strip().lower()
        return ans == "y"
    except (EOFError, KeyboardInterrupt):
        return False


# ── 로그 저장 ────────────────────────────────────────────────────────────────

def append_log(log_data: dict) -> None:
    log_file = ROOT / "data" / "eum_task_log.json"
    logs = []
    if log_file.exists():
        try:
            logs = json.loads(log_file.read_text(encoding="utf-8"))
        except Exception:
            logs = []
    logs.append(log_data)
    log_file.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 업무별 실행 함수 ─────────────────────────────────────────────────────────

def run_comm_alert(analysis: dict, dry_run: bool) -> int:
    """통신단절 단말기 알림 메일"""
    targets = analysis["comm_critical"] + analysis["comm_warn"]
    print(f"\n{'='*70}")
    print(f"[업무1] 통신단절 알림 메일 | 대상: {len(targets)}개")
    print(f"  심각(100일↑): {len(analysis['comm_critical'])}개  |  주의(30~99일): {len(analysis['comm_warn'])}개")
    print("="*70)

    sent = 0
    for i, d in enumerate(targets, 1):
        mail = mail_comm_alert(d)
        level = "🔴 긴급" if d["_단절일수"] >= 100 else "🟡 주의"
        print(f"\n  [{i}/{len(targets)}] {level} NO.{d['NO']} | {d['공사명'][:40]}")
        print(f"  공사업체: {d['공사업체']} | 단절: {d['_단절일수']}일 | 관할: {d['관할지사']}")
        print(f"  제목: {mail['subject']}")

        if dry_run:
            print("  → [DRY-RUN] 발송 생략")
            continue

        to = input("  수신 이메일 (skip=건너뜀): ").strip()
        if not to or to.lower() == "skip":
            print("  → 건너뜀")
            continue

        print(f"  → 발송 중: {to}")
        ok = send_gmail(to, mail["subject"], mail["body"])
        status = "발송완료" if ok else "발송실패"
        print(f"  → {status}")
        append_log({
            "일시": TODAY.isoformat(), "업무": "통신단절알림",
            "NO": d["NO"], "공사명": d["공사명"], "수신": to, "상태": status
        })
        if ok:
            sent += 1
        time.sleep(1)

    print(f"\n  ✓ 통신단절 알림: {sent}건 발송 완료 (건너뜀 {len(targets)-sent}건)")
    return sent


def run_unused_notice(analysis: dict, dry_run: bool) -> int:
    """미사용 단말기 사용 안내 메일"""
    targets = analysis["unused"]
    print(f"\n{'='*70}")
    print(f"[업무2] 미사용 단말기 사용 안내 메일 | 대상: {len(targets)}개")
    print("="*70)

    sent = 0
    for i, d in enumerate(targets, 1):
        mail = mail_unused_notice(d)
        print(f"\n  [{i}/{len(targets)}] NO.{d['NO']} | {d['공사명'][:40]}")
        print(f"  공사업체: {d['공사업체']} | 설치일수: {d.get('설치일수','?')}일 | 처리건수: 0")
        print(f"  제목: {mail['subject']}")

        if dry_run:
            print("  → [DRY-RUN] 발송 생략")
            continue

        to = input("  수신 이메일 (skip=건너뜀): ").strip()
        if not to or to.lower() == "skip":
            print("  → 건너뜀")
            continue

        print(f"  → 발송 중: {to}")
        ok = send_gmail(to, mail["subject"], mail["body"])
        status = "발송완료" if ok else "발송실패"
        print(f"  → {status}")
        append_log({
            "일시": TODAY.isoformat(), "업무": "미사용안내",
            "NO": d["NO"], "공사명": d["공사명"], "수신": to, "상태": status
        })
        if ok:
            sent += 1
        time.sleep(1)

    print(f"\n  ✓ 미사용 안내: {sent}건 발송 완료")
    return sent


def run_promo(dry_run: bool, limit: int = 20) -> int:
    """신규 현장 S/A등급 홍보 메일 발송"""
    sites = load_priority_sites()
    # 이메일 있는 것만
    sites = [s for s in sites if s.get("이메일", "").strip()]
    print(f"\n{'='*70}")
    print(f"[업무3] 신규 현장 홍보 메일 | 전체 S/A등급: {len(sites)}개")
    print(f"  이번 실행: 상위 {limit}개만 처리 (전체 발송 시 --limit 옵션 사용)")
    print("="*70)

    targets = sites[:limit]
    sent = 0
    for i, p in enumerate(targets, 1):
        mail = mail_promo(p)
        print(f"\n  [{i}/{len(targets)}] {p.get('점수','?')}점 | {p['공사명'][:40]}")
        print(f"  업체: {p['업체명']} | 이메일: {p['이메일']}")
        print(f"  근거: {p.get('근거','')}")
        print(f"  제목: {mail['subject'][:60]}")

        if dry_run:
            print("  → [DRY-RUN] 발송 생략")
            sent += 1
            continue

        if not confirm(f"  [{i}/{len(targets)}] 위 업체에 홍보 메일 발송하시겠습니까?"):
            print("  → 건너뜀")
            continue

        print(f"  → 발송 중: {p['이메일']}")
        ok = send_gmail(p["이메일"], mail["subject"], mail["body"])
        status = "발송완료" if ok else "발송실패"
        print(f"  → {status}")
        append_log({
            "일시": TODAY.isoformat(), "업무": "홍보메일",
            "NO": p.get("NO"), "공사명": p["공사명"],
            "업체명": p["업체명"], "수신": p["이메일"], "상태": status
        })
        if ok:
            sent += 1
        time.sleep(2)

    print(f"\n  ✓ 홍보 메일: {sent}건 발송 완료")
    return sent


def run_fault_query() -> None:
    """고장신고내역 조회 (WEBMAN420M00)"""
    print(f"\n{'='*70}")
    print("[업무4] 고장신고내역 조회 (WEBMAN420M00)")
    print("="*70)

    try:
        from scripts.web_connector import get_page
        page = get_page()

        print("  → EUM 고장신고내역 페이지 접속 중...")
        page.goto("https://eum.cw.or.kr/web/man/WEBMAN420M00", timeout=30000)
        page.wait_for_load_state("load", timeout=8000)

        try:
            from scripts.popup_detector import handle_page_popups
            handle_page_popups(page, timeout_s=2.0)
        except Exception:
            pass

        # 조회 기간: 전체 (2020-01-01 ~ 오늘)
        page.evaluate("""
        (() => {
            const inputs = document.querySelectorAll('input[type="text"]');
            for (let inp of inputs) {
                if (inp.placeholder?.includes('시작') || inp.id?.includes('Start') || inp.id?.includes('start')) {
                    inp.value = '2020-01-01';
                    inp.dispatchEvent(new Event('change', {bubbles:true}));
                    inp.dispatchEvent(new Event('input', {bubbles:true}));
                }
                if (inp.placeholder?.includes('종료') || inp.placeholder?.includes('끝') ||
                    inp.id?.includes('End') || inp.id?.includes('end')) {
                    inp.value = arguments[0];
                    inp.dispatchEvent(new Event('change', {bubbles:true}));
                    inp.dispatchEvent(new Event('input', {bubbles:true}));
                }
            }
            // datepicker 형태
            const dps = document.querySelectorAll('[class*="datepicker"], [class*="DatePicker"]');
            console.log('datepicker 개수:', dps.length);
        })();
        """)
        time.sleep(0.5)

        # 100개씩
        page.evaluate("""
        (() => {
            for (let sel of document.querySelectorAll('select')) {
                const o = Array.from(sel.options).find(o => o.text.includes('100'));
                if (o) { sel.value = o.value; sel.dispatchEvent(new Event('change', {bubbles:true})); }
            }
        })();
        """)

        # 조회 버튼
        page.evaluate("""
        (() => {
            for (let btn of document.querySelectorAll('button')) {
                if (btn.innerText?.trim() === '조회') { btn.click(); return; }
            }
        })();
        """)
        time.sleep(2)

        # 데이터 파싱
        rows = page.evaluate("""
        (() => {
            const tables = document.querySelectorAll('table');
            if (!tables.length) return [];
            // 데이터 테이블 찾기
            let dataTable = null;
            for (let t of tables) {
                const trs = t.querySelectorAll('tr');
                if (trs.length > 2) { dataTable = t; break; }
            }
            if (!dataTable) return [];
            const out = [];
            dataTable.querySelectorAll('tr').forEach(tr => {
                const tds = tr.querySelectorAll('td');
                if (tds.length > 0) {
                    out.push(Array.from(tds).map(td => td.innerText?.trim() || ''));
                }
            });
            return out;
        })();
        """)

        # 빈 결과 확인
        no_data = page.evaluate("""
        (() => {
            const text = document.body?.innerText || '';
            return text.includes('조회된 내역이 없습니다') || text.includes('검색된 결과가 없');
        })();
        """)

        if no_data or not rows:
            print("  → 고장신고 내역 없음 (조회 기간 내 접수 건 없음)")
            _save_fault_result([], "없음")
            return

        # 헤더: NO, 공제가입번호, 단말기번호, 고유번호, 단말기ID, 고장신고번호, 신고내용, 수신연락처, 신고일자, 처리일자, 처리상태, 비고
        headers = ["NO", "공제가입번호", "단말기번호", "고유번호", "단말기ID",
                   "고장신고번호", "신고내용", "수신연락처", "신고일자", "처리일자", "처리상태", "비고"]

        faults = []
        for r in rows:
            if r and r[0].isdigit():
                item = {headers[i]: r[i] if i < len(r) else "" for i in range(len(headers))}
                faults.append(item)

        print(f"  → 고장신고 {len(faults)}건 조회")

        unresolved = [f for f in faults if "미처리" in f.get("처리상태", "") or f.get("처리상태", "") == ""]
        print(f"  → 미처리: {len(unresolved)}건")

        for f in faults:
            status_mark = "🔴" if "미처리" in f.get("처리상태", "") else "✅"
            print(f"  {status_mark} [{f['NO']}] {f.get('신고내용','')[:30]} | {f.get('신고일자','')} | {f.get('처리상태','')}")

        _save_fault_result(faults, f"{len(faults)}건")

    except Exception as e:
        _log.error(f"고장신고 조회 실패: {e}")
        import traceback
        traceback.print_exc()


def _save_fault_result(faults: list, summary: str) -> None:
    out = ROOT / "data" / f"eum_fault_report_{TODAY.strftime('%Y%m%d')}.json"
    out.write_text(json.dumps({
        "기준일": TODAY.isoformat(),
        "source": "WEBMAN420M00",
        "summary": summary,
        "total": len(faults),
        "미처리": [f for f in faults if "미처리" in f.get("처리상태", "")],
        "전체": faults
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ 저장: {out.name}")


# ── 메인 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="EUM 업무 자동화 실행기")
    parser.add_argument("--dry-run", action="store_true", help="발송 없이 초안 확인만")
    parser.add_argument("--task", default="all",
                        choices=["all", "comm", "unused", "promo", "fault"],
                        help="실행할 업무 (기본: all)")
    parser.add_argument("--limit", type=int, default=20,
                        help="홍보 메일 최대 발송 수 (기본: 20)")
    args = parser.parse_args()

    print("\n" + "="*70)
    print("  해한소방 EUM 업무 자동화 실행기")
    print(f"  기준일: {TODAY}  |  모드: {'DRY-RUN' if args.dry_run else '실제 발송'}  |  업무: {args.task}")
    print("="*70)

    if args.dry_run:
        print("\n⚠  DRY-RUN 모드: 메일 발송 없이 내용만 출력합니다.\n")

    devices = load_devices()
    analysis = analyze(devices)

    print(f"\n[현황 요약]")
    print(f"  임대 중: {len(devices)}대")
    print(f"  통신단절 심각(100일↑): {len(analysis['comm_critical'])}대")
    print(f"  통신단절 주의(30~99일): {len(analysis['comm_warn'])}대")
    print(f"  미사용 의심: {len(analysis['unused'])}대")

    total_sent = 0

    if args.task in ("all", "comm"):
        total_sent += run_comm_alert(analysis, args.dry_run)

    if args.task in ("all", "unused"):
        total_sent += run_unused_notice(analysis, args.dry_run)

    if args.task in ("all", "promo"):
        total_sent += run_promo(args.dry_run, limit=args.limit)

    if args.task in ("all", "fault"):
        run_fault_query()

    print(f"\n{'='*70}")
    print(f"  실행 완료 | 총 {total_sent}건 처리")
    print(f"  로그: data/eum_task_log.json")
    print("="*70 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠  사용자 중단")
        sys.exit(0)
    except Exception as e:
        _log.error(f"실행 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
