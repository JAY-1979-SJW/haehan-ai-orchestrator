"""EUM 영업대상 3,297건 개별 메일 발송 (SMTP, 엑셀 본문 그대로)."""

import contextlib
import json
import logging
import os
import smtplib
import time
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
TARGETS_FILE = ROOT / "data" / "eum_new_sites_install_targets.json"
LOG_FILE = ROOT / "data" / "eum_mail_send_log.json"

SMTP_HOST = "mailapp.hiworks.co.kr"
SMTP_PORT = 25
ACCOUNT = os.getenv("HIWORKS_MAIL_ACCOUNT")
PASSWORD = os.getenv("HIWORKS_MAIL_PASSWORD")

SUBJECT = "전자카드 단말기 임대시 AI 안전서류 무상제공"

BODY_TEMPLATE = """\
안녕하세요, {업체명} 담당자님.

"{공사명}" 현장 계약을 진심으로 축하드립니다.
해한AI엔지니어링 담당 신재우입니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
전자카드 단말기, 쓰면 원청이 더 법니다.
월 96,800원 임대 · 자부담 0원 · 임대비 100% 정산 · 이윤↑ · AI 안전서류+CAD 무상제공
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 2024.1.1부터 공공공사(1억 이상)·민간공사(50억 이상)는 건설근로자 전자카드 단말기가
   의무사용이며, 미사용 시 과태료(3차 적용 시 최대 600만원)가 부과됩니다.

2. 저희는 건설근로자공제회 공인 제조사(비전아이) 인증 공급업체로, 비전아이 T900
   단말기(월 96,800원 임대, 2024년 운영평가 S등급 1위)를 공급하며 관급공사 200개
   현장(약 200억)을 운영 중인 단말기 설치·운영 전문업체입니다.

■ 단말기를 쓰면 원청에 남는 이유 (20억 공사 원가계산 예시)
┌─────────────────────────┬──────────────┬──────────────┬────────────┬──────────────┐
│ 항목                    │ 단말기 미사용 │ T900 적용    │ 증감       │ 효과         │
├─────────────────────────┼──────────────┼──────────────┼────────────┼──────────────┤
│ 퇴직공제부금비(직노×2.3%)│ 46,000,000   │ 47,161,600   │▲1,161,600  │ 부금비용서정산│
│ 일반관리비(재+노+경×5.5%)│268,742,467   │268,806,355   │   ▲63,888  │ 정산금액 상승 │
│ 이윤(노+경+일관×15%)    │473,245,373   │473,429,196   │  ▲183,823  │ 순이득       │
└─────────────────────────┴──────────────┴──────────────┴────────────┴──────────────┘
※ 임대비용(월 96,800원 × 12 = 연 1,161,600원)은 원가계산서(퇴직공제부금)에서 100% 정산
   → 실부담 0원. 단말기 적용 시 일반관리비 +63,888원 · 이윤 +183,823원 = 순이득 +247,711원 추가 발생.

■ 해한AI엔지니어링만의 추가 혜택
· 계약 완료 후 2일 내 단말기 수령 + 직접 현장 설치
· 환급서류 작성 → 컨설팅 → 환급처리까지 전 과정 대행
· 자체 프로그램이 통신단절·미작동 단말기 자동 감지 → 정기 현황 리포트 발송 (정산 누락 0)
· AI 프로그램 2종 무상제공 (하단 상세 안내 참조)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ AI ① 안전서류 생성기 — 무료 제공 (kras.haehan-ai.kr)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"도면 보여줘. 소방 물량 뽑아줘." — 말 한마디로 끝납니다.

· 2024년부터 5인 이상 사업장 전면 적용 — 공사 현장은 예외 없이 위험성평가 의무 작성.
  미작성·부실 작성 시 과태료·형사처벌 대상.

· 문제는 시간입니다 — 현장마다 위험요인이 다르고, 작업 공정별로 따로 작성해야 해서
  소장 혼자 처리하기엔 수십 장이 넘습니다.

· AI가 현장 정보 입력만 하면 위험요인 자동 분석 → 공정별 평가표 자동 생성
  — 기존 반나절 작업을 10분으로 단축.

· 법적 요건(고용노동부 기준) 충족 형식으로 자동 완성 — 감독관 점검 시 즉시 제출 가능한 완성본 출력.

· 한 번 작성한 현장 정보는 저장 → 다음 공사에서 재활용, 유사 현장은 클릭 몇 번으로 완성.

· 단말기 설치 현장 전원 무료 제공 → kras.haehan-ai.kr

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
■ AI ② AI-CAD 연동 물량산출·작도 — 시연 후 체험 제공 (cad.haehan-ai.kr)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

· 기존 CAD 프로그램과 다릅니다 — 명령어·마우스 조작 없이 AI 대화창에 자연어로 지시하거나
  버튼 클릭만으로 물량산출·작도 완료.

· 지원 공종: 건축·구조·기계설비·전기·통신·소방 — 도면 업로드 한 번으로 전 공종 동시 산출.

· AutoCAD 직접 연동: "이 구간 벽체 및 배관 작도해줘" 한 마디로 도면에 바로 반영.

· 물량산출서·견적서·준공도면 — AI가 대신 작성. 서류 때문에 야근하는 일이 줄어듭니다.

· 발주처 제출 서류도 도면 기반으로 자동 정리 — 한 번에 완성.

· 단말기 설치 현장에 직접 방문 시연 후 체험 기간 제공 → cad.haehan-ai.kr

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▶ 연락 주시면 귀 현장의 설치 일정·필요 대수·예상 정산액을 정리해 바로 전달드리겠습니다.
   긍정적인 검토 부탁드립니다.

해한AI엔지니어링  |  담당 신재우
전화 010-7387-6635  |  팩스 02-6442-6665  |  이메일 jay@haehan-ai.kr
홈페이지 haehan-ai.kr
서울특별시 강동구 고덕비즈밸리로 26길 B동 325호  |  전문소방시설공사업 등록 제2021-02-00139호

※ 본 메일은 건설근로자공제회 등록 현장 담당자에게 발송됩니다.
   수신거부: 02-6442-6665로 연락 주시면 즉시 발송 중단합니다.
"""


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


def load_sent_log() -> dict:
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text(encoding="utf-8"))
    return {"sent": [], "failed": []}


def save_log(log: dict):
    LOG_FILE.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def send_one(server: smtplib.SMTP, row: dict) -> bool:
    email = (row.get("이메일") or "").strip()
    company = (row.get("업체명") or "담당자").strip()
    project = (row.get("공사명") or "").strip()
    if not email or "@" not in email:
        return False

    body = BODY_TEMPLATE.format(업체명=company, 공사명=project)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(SUBJECT, "utf-8")
    from email.utils import formataddr

    msg["From"] = formataddr((Header("해한AI엔지니어링 신재우", "utf-8").encode(), ACCOUNT))
    msg["To"] = email
    msg.attach(MIMEText(body, "plain", "utf-8"))

    server.sendmail(ACCOUNT, [email], msg.as_string())
    return True


def connect_smtp() -> smtplib.SMTP:
    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
    server.ehlo()
    server.login(ACCOUNT, PASSWORD)
    return server


def main(dry_run: bool = False, limit: int | None = None, start_from: int = 0):
    rows = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))

    # 2025년 이후 필터
    rows = [
        r
        for r in rows
        if (r.get("공사시작일") or "")[:4] >= "2025"
        or not (r.get("공사시작일") or "").strip()
        or (r.get("공사시작일") or "").strip() == "-"
    ]

    log = load_sent_log()
    sent_emails = {e["email"] for e in log["sent"]}

    # 이미 발송된 것 제외
    targets = [r for r in rows if (r.get("이메일") or "").strip() not in sent_emails]
    targets = targets[start_from:]
    if limit:
        targets = targets[:limit]

    logger.info("발송 대상: %d건 (전체 %d건, 기발송 제외)", len(targets), len(rows))

    if dry_run:
        logger.info("=== DRY RUN — 실제 발송 안 함 ===")
        for i, r in enumerate(targets[:5], 1):
            logger.info("[%d] %s → %s", i, r.get("업체명"), r.get("이메일"))
        return

    server = connect_smtp()
    reconnect_count = 0

    for i, row in enumerate(targets, 1):
        email = (row.get("이메일") or "").strip()
        try:
            # 100건마다 재연결
            if i % 100 == 0:
                # SMTP 재연결 실패 무시 - 개별 발송 실패는 failed 로그에 별도 기록(성공/실패 은폐 없음)
                with contextlib.suppress(Exception):
                    server.quit()
                server = connect_smtp()
                reconnect_count += 1

            ok = send_one(server, row)
            if ok:
                log["sent"].append(
                    {
                        "email": email,
                        "company": row.get("업체명"),
                        "project": row.get("공사명"),
                        "seq": i,
                    }
                )
                logger.info("[%d/%d] ✓ %s → %s", i, len(targets), row.get("업체명"), email)
            else:
                log["failed"].append({"email": email, "reason": "invalid_email", "row": row})
                logger.warning("[%d/%d] ✗ 이메일 없음: %s", i, len(targets), row.get("업체명"))

        except Exception as e:  # noqa: BLE001 - EUM 영업메일 배치 발송 스크립트 — except는 SMTP 재연결 실패 무시, 개별 발송 실패를 failed 로그에 기록 후 다음 건 계속, 최종 서버 종료 실패 무시. 각 건의 성공/실패는 sent/failed 리스트에 명시적으로 구분 기록되어 실패가 성공으로 은폐되지 않음.
            logger.error("[%d/%d] ✗ 발송 실패 %s: %s", i, len(targets), email, e)
            log["failed"].append({"email": email, "reason": str(e), "row": row})
            # SMTP 재연결 실패 무시 - 다음 건은 send_one() 내부에서 다시 실패 처리됨
            with contextlib.suppress(Exception):
                server = connect_smtp()

        # 로그 저장 (10건마다)
        if i % 10 == 0:
            save_log(log)

        time.sleep(1.5)  # 발송 간격 1.5초

    # 최종 서버 종료 실패 무시 - 배치는 이미 완료, sent/failed 로그가 실제 결과를 별도로 보존
    with contextlib.suppress(Exception):
        server.quit()

    save_log(log)
    logger.info("완료 — 성공:%d 실패:%d 재연결:%d", len(log["sent"]), len(log["failed"]), reconnect_count)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--start-from", type=int, default=0)
    args = parser.parse_args()
    main(dry_run=args.dry_run, limit=args.limit, start_from=args.start_from)
