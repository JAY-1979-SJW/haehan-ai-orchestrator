"""Prepare sales-mail targets and drafts from EUM new-site data.

This module is intentionally preparation-only. It reads discovered install
targets, ranks them, and writes draft files. It never sends mail.
"""

from __future__ import annotations

import json
import json as _json_for_db
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from scripts.common.app_paths import repo_root

ROOT = repo_root()


def _eum_dir() -> Path:
    from scripts.common.data_paths import get_app_dir

    return get_app_dir("eum")


DATA_DIR = _eum_dir()
DEFAULT_SOURCE = DATA_DIR / "eum_new_sites_install_targets.json"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class SalesMailTarget:
    rank: int
    grade: str
    score: int
    email: str
    subject: str
    project_name: str
    company: str
    manager: str
    phone: str
    address: str
    branch: str
    install_date: str
    registered_date: str
    start_date: str
    end_date: str
    project_no: str
    mutual_aid_no: str
    reasons: list[str]
    body: str


def load_new_site_projects(source: str | Path = DEFAULT_SOURCE) -> list[dict[str, Any]]:
    """Load project rows from the EUM new-site extraction file."""
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"new-site source file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("projects"), list):
        rows = payload["projects"]
    else:
        raise ValueError("new-site source must be a list or contain a projects list")

    return [row for row in rows if isinstance(row, dict)]


def normalize_project(row: dict[str, Any]) -> dict[str, str]:
    """Normalize EUM project fields to stable internal names."""

    def pick(*names: str) -> str:
        for name in names:
            value = row.get(name)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    return {
        "project_no": pick("공사번호", "project_no"),
        "mutual_aid_no": pick("공제가입번호", "mutual_aid_no"),
        "project_name": pick("공사명", "project_name"),
        "address": pick("현장주소", "address"),
        "company": pick("업체명", "company"),
        "install_date": pick("설치예정일", "install_date"),
        "install_count": pick("설치예정대수", "install_count"),
        "branch": pick("관할지사", "branch"),
        "manager": pick("담당자", "manager"),
        "phone": pick("연락처", "phone"),
        "email": pick("이메일", "email").lower(),
        "registered_date": pick("등록일", "registered_date"),
        "start_date": pick("공사시작일", "start_date"),
        "end_date": pick("공사종료일", "end_date"),
    }


def parse_date(value: str) -> date | None:
    """Parse a YYYY-MM-DD-ish date string."""
    text = (value or "").strip()
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _score_install_date(install_date: date | None, today: date) -> tuple[int, str] | None:
    """설치예정일 기준 (점수, 사유). 날짜가 없으면 None."""
    if not install_date:
        return None
    days_to_install = (install_date - today).days
    if days_to_install < 0:
        return 30, "설치예정일 경과"
    if days_to_install <= 30:
        return 25, "30일 이내 설치 예정"
    if days_to_install <= 90:
        return 15, "90일 이내 설치 예정"
    return 5, "장기 설치 예정"


def _score_registered_date(registered_date: date | None, today: date) -> tuple[int, str] | None:
    """등록일 기준 (점수, 사유). 날짜가 없거나 해당 구간이 아니면 None."""
    if not registered_date:
        return None
    days_since_registered = (today - registered_date).days
    if 0 <= days_since_registered <= 30:
        return 20, "최근 등록 현장"
    if days_since_registered <= 60:
        return 10, "60일 이내 등록"
    if days_since_registered <= 90:
        return 5, "90일 이내 등록"
    return None


def _score_end_date(end_date: date | None, today: date) -> tuple[int, str] | None:
    """공사종료일(잔여 공기) 기준 (점수, 사유). 날짜가 없거나 해당 구간이 아니면 None."""
    if not end_date:
        return None
    remaining_days = (end_date - today).days
    if remaining_days >= 365:
        return 35, "잔여 공기 12개월 이상"
    if remaining_days >= 180:
        return 25, "잔여 공기 6개월 이상"
    if remaining_days >= 60:
        return 10, "잔여 공기 2개월 이상"
    return None


def score_project(project: dict[str, str], today: date | None = None) -> tuple[int, str, list[str]]:
    """Score a new-site project for practical sales priority."""
    today = today or date.today()
    score = 0
    reasons: list[str] = []

    install_date = parse_date(project.get("install_date", ""))
    registered_date = parse_date(project.get("registered_date", ""))
    end_date = parse_date(project.get("end_date", ""))

    for date_score in (
        _score_install_date(install_date, today),
        _score_registered_date(registered_date, today),
        _score_end_date(end_date, today),
    ):
        if date_score is not None:
            score += date_score[0]
            reasons.append(date_score[1])

    branch = project.get("branch", "")
    if any(token in branch for token in ("서울", "경기", "인천", "의정부", "수원", "성남", "안양")):
        score += 10
        reasons.append("수도권 관할")

    if project.get("email") and EMAIL_RE.match(project["email"]):
        score += 10
        reasons.append("이메일 확보")

    if project.get("phone"):
        score += 5
        reasons.append("연락처 확보")

    grade = "A" if score >= 80 else "B" if score >= 55 else "C"
    return score, grade, reasons


def build_mail_body(project: dict[str, str], sender_name: str = "해한소방 단말기사업팀") -> str:
    """Build a Korean sales-mail draft for one project."""
    manager = project.get("manager") or "담당자"
    company = project.get("company") or "귀사"
    project_name = project.get("project_name") or "해당 현장"
    install_date = project.get("install_date") or "확인 필요"
    end_date = project.get("end_date") or "확인 필요"
    branch = project.get("branch") or "확인 필요"

    return (
        f"{company} {manager}님 안녕하세요.\n\n"
        f"{project_name} 현장의 건설근로자공제회 전자카드 단말기 설치 안내드립니다.\n"
        f"EUM 설치안내대상에 등록된 현장으로 확인되어, 설치 일정과 필요 대수를 사전에 맞춰드리고자 연락드립니다.\n\n"
        f"- 현장명: {project_name}\n"
        f"- 설치예정일: {install_date}\n"
        f"- 공사종료일: {end_date}\n"
        f"- 관할지사: {branch}\n\n"
        "전자카드 단말기 설치, 개통, 현장 적용 방법까지 한 번에 안내 가능합니다.\n"
        "회신 주시면 설치 가능 일정과 준비사항을 정리해서 바로 전달드리겠습니다.\n\n"
        f"감사합니다.\n{sender_name}\n"
        "이메일: skyjwshin@gmail.com\n"
    )


def _make_target(idx: int, project: dict[str, Any]) -> SalesMailTarget:
    """점수가 매겨진 프로젝트 1건을 영업 메일 대상으로 변환."""
    subject = f"[건설e음 전자카드 단말기 설치 안내] {project.get('project_name') or '현장'}"
    body = build_mail_body(project)
    return SalesMailTarget(
        rank=idx,
        grade=project["grade"],
        score=int(project["score"]),
        email=project["email"],
        subject=subject,
        project_name=project.get("project_name", ""),
        company=project.get("company", ""),
        manager=project.get("manager", ""),
        phone=project.get("phone", ""),
        address=project.get("address", ""),
        branch=project.get("branch", ""),
        install_date=project.get("install_date", ""),
        registered_date=project.get("registered_date", ""),
        start_date=project.get("start_date", ""),
        end_date=project.get("end_date", ""),
        project_no=project.get("project_no", ""),
        mutual_aid_no=project.get("mutual_aid_no", ""),
        reasons=list(project["reasons"]),
        body=body,
    )


def prepare_sales_mail(
    *,
    source: str | Path = DEFAULT_SOURCE,
    output_dir: str | Path = DATA_DIR,
    limit: int = 30,
    min_grade: str = "A",
    today: date | None = None,
) -> dict[str, Any]:
    """Rank EUM new sites and write sales-mail draft artifacts."""
    rows = load_new_site_projects(source)
    normalized = [normalize_project(row) for row in rows]

    min_grade = (min_grade or "A").upper()
    grade_floor = {"A": 3, "B": 2, "C": 1}.get(min_grade, 3)

    seen: set[tuple[str, str]] = set()
    scored: list[dict[str, Any]] = []
    for project in normalized:
        email = project.get("email", "")
        if not EMAIL_RE.match(email):
            continue
        key = (email, project.get("project_name", ""))
        if key in seen:
            continue
        seen.add(key)
        score, grade, reasons = score_project(project, today=today)
        if {"A": 3, "B": 2, "C": 1}[grade] < grade_floor:
            continue
        scored.append({**project, "score": score, "grade": grade, "reasons": reasons})

    scored.sort(key=lambda item: (-int(item["score"]), item["install_date"], item["project_name"]))
    selected = scored[: max(0, int(limit))]

    targets = [_make_target(idx, project) for idx, project in enumerate(selected, start=1)]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    json_path = output_dir / f"eum_sales_mail_targets_{stamp}.json"
    text_path = output_dir / f"eum_sales_mail_drafts_{stamp}.txt"
    queue_path = output_dir / f"eum_sales_mail_queue_{stamp}.jsonl"
    latest_json = output_dir / "eum_sales_mail_targets_latest.json"
    latest_text = output_dir / "eum_sales_mail_drafts_latest.txt"
    latest_queue = output_dir / "eum_sales_mail_queue_latest.jsonl"

    payload = {
        "timestamp": datetime.now().isoformat(),
        "source": str(Path(source)),
        "total_projects": len(rows),
        "eligible_targets": len(scored),
        "selected_targets": len(targets),
        "limit": limit,
        "min_grade": min_grade,
        "send_status": "not_sent_prepare_only",
        "targets": [asdict(target) for target in targets],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    draft_blocks = []
    for target in targets:
        draft_blocks.append(
            "\n".join(
                [
                    "=" * 72,
                    f"Rank: {target.rank} / Grade: {target.grade} / Score: {target.score}",
                    f"To: {target.email}",
                    f"Subject: {target.subject}",
                    f"Project: {target.project_name}",
                    f"Reasons: {', '.join(target.reasons)}",
                    "-" * 72,
                    target.body,
                ]
            )
        )
    text_path.write_text("\n\n".join(draft_blocks), encoding="utf-8")
    queue_rows: list[dict[str, Any]] = []
    for target in targets:
        queue_rows.append(
            {
                "status": "pending",
                "provider": "company_mail",
                "to": target.email,
                "subject": target.subject,
                "body": target.body,
                "metadata": {
                    "rank": target.rank,
                    "grade": target.grade,
                    "score": target.score,
                    "project_no": target.project_no,
                    "project_name": target.project_name,
                    "company": target.company,
                    "manager": target.manager,
                    "phone": target.phone,
                },
            }
        )
    queue_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in queue_rows),
        encoding="utf-8",
    )
    try:
        from scripts.browser.cdp import cdp_db

        cdp_db.init_db()
        run_id = cdp_db.log_automation_run(
            "eum",
            "sales_mail_prepare",
            command="python scripts/entry/cdp_cli.py eum sales-mail",
            status="success",
            risk_level="auto",
            input_ref=str(Path(source)),
            output_ref=str(queue_path),
            detail=f"selected={len(targets)} eligible={len(scored)}",
        )
        for row in queue_rows:
            cdp_db.upsert_mail_queue_item(
                provider="hiworks",
                source=f"eum_sales_mail:{run_id}",
                recipient=row["to"],
                subject=row["subject"],
                body=row["body"],
                status=row["status"],
                metadata=_json_for_db.dumps(row.get("metadata") or {}, ensure_ascii=False),
            )
    except Exception:  # noqa: BLE001 - 영업메일 준비 결과를 cdp_db에 부가 기록(log_automation_run/upsert_mail_queue_item)하는 단계 실패 시 무시 - 실제 큐 파일(json/text/queue)은 이미 write_text로 저장 완료된 뒤이고, 메일은 status=pending으로만 큐잉될 뿐 자동발송 없음, DB 기록 실패가 발송 승인을 우회하지 않음
        pass
    shutil.copyfile(json_path, latest_json)
    shutil.copyfile(text_path, latest_text)
    shutil.copyfile(queue_path, latest_queue)

    return {**payload, "json_path": str(json_path), "text_path": str(text_path), "queue_path": str(queue_path)}


def print_summary(result: dict[str, Any]) -> None:
    """Print a compact CLI summary."""
    print("=" * 60)
    print("EUM sales-mail preparation")
    print("=" * 60)
    print(f"source projects: {result['total_projects']}")
    print(f"eligible targets: {result['eligible_targets']}")
    print(f"selected drafts: {result['selected_targets']}")
    print(f"send status: {result['send_status']}")
    print(f"json: {result['json_path']}")
    print(f"text: {result['text_path']}")
    print(f"queue: {result['queue_path']}")
    for target in result.get("targets", [])[:5]:
        print(f"- #{target['rank']} {target['grade']} {target['score']} {target['email']} {target['project_name']}")


def main(limit: int = 30, min_grade: str = "A") -> dict[str, Any]:
    result = prepare_sales_mail(limit=limit, min_grade=min_grade)
    print_summary(result)
    return result


if __name__ == "__main__":
    main()
