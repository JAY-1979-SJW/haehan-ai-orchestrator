from pathlib import Path

import yaml

from ai_orchestrator.core.models import ExecutionPlan, RiskAssessment, TaskRequest
from scripts.common.app_paths import repo_root

# 결함(2026-10-09, PR165 CI 조사 중 발견 — tools/gates/policy.py 가 한 폴더 더 깊이 있던
# 시절 계산(parents[1])이 move 이후에도 안 바뀌어 tools/policies/ 라는 없는 경로를 가리켰다.
# 정본은 저장소 루트 policies/(allowed_paths·blocked_paths 전체가 있는 97줄짜리) — 이동뒤
# 더 안전하게 repo_root() 로 고정.
DEFAULT_POLICY_PATH = repo_root() / "policies" / "default_policy.yaml"


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def evaluate_request(req: TaskRequest, risk: RiskAssessment, policy: dict) -> ExecutionPlan:
    allowed = True
    requires_approval = risk.requires_approval
    blocked_reasons = []

    blocked_paths = policy.get("blocked_paths", [])
    blocked_commands = policy.get("blocked_commands", [])
    allowed_paths = policy.get("allowed_paths", [])

    # 차단 경로 검사
    for bp in blocked_paths:
        if bp.lower() in req.target.lower():
            allowed = False
            blocked_reasons.append(f"차단 경로 일치: {bp}")

    # 차단 명령어 검사
    payload_str = str(req.payload).lower()
    for bc in blocked_commands:
        if bc.lower() in payload_str or bc.lower() in req.target.lower():
            allowed = False
            blocked_reasons.append(f"차단 명령어 일치: {bc}")

    # critical 기본 차단
    if risk.risk_level == "critical":
        allowed = False
        blocked_reasons.append("critical 위험도: 기본 차단 (화이트리스트 필요)")

    # allowed_paths 밖 쓰기 요청 차단
    if risk.risk_level in ("medium", "high"):
        in_allowed = any(ap.lower() in req.target.lower() for ap in allowed_paths)
        # URL 기반 read-only action 은 filesystem allowed_paths 검사에서 제외.
        # 대신 executor 단계의 whitelist + playwright_connector.validate_url 로 차단한다.
        _path_exempt_actions = (
            "run_shell",
            "restart_service",
            "deploy_app",
            "push_git",
            "fetch_web_page",
        )
        if not in_allowed and req.action_type not in _path_exempt_actions:
            allowed = False
            blocked_reasons.append(f"허용 경로 밖 수정 요청: {req.target}")

    steps = _build_steps(req, risk, allowed, requires_approval)

    return ExecutionPlan(
        task_id=req.task_id,
        allowed=allowed,
        requires_approval=requires_approval,
        steps=steps,
        blocked_reasons=blocked_reasons,
    )


def _build_steps(req, risk, allowed, requires_approval) -> list:
    steps = [
        f"[1] 작업 수신: {req.description}",
        f"[2] 위험도 분류: {risk.risk_level.upper()} ({', '.join(risk.reasons)})",
    ]
    if not allowed:
        steps.append("[3] 정책 검사: 차단됨")
        steps.append("[4] 실행 중단")
    elif requires_approval:
        steps.append("[3] 정책 검사: 통과 (승인 필요)")
        steps.append("[4] 실행 보류 (승인 대기)")
    else:
        steps.append("[3] 정책 검사: 자동 허용")
        steps.append("[4] 드라이런 실행 (실제 변경 없음)")
    return steps
