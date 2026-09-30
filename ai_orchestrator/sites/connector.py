"""사이트 커넥터 공통 인터페이스.

규칙:
- execute() 는 이번 단계에서 실제 고위험 제출을 수행하지 않는다.
- 미구현 액션은 SiteExecutionResult(status="not_implemented" 또는 "unsupported_action") 로 반환.
- 커넥터별 예외는 ConnectorError 로 공통화한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from .models import SiteExecutionResult, SiteHealthStatus, SiteTask


class ConnectorError(Exception):
    """커넥터 공통 예외. message 에 민감 원문을 담지 않는다."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message


class SiteConnector(ABC):
    """사이트별 자동화 커넥터 베이스.

    구현 주의:
    - 로그/반환값에 비밀번호, 쿠키 원문, storage state 원문, Authorization 헤더 원문 금지.
    - health_check / login_check 는 "안전한 읽기성 점검" 이어야 한다.
      절대 제출/수정/삭제 같은 상태 변경 동작을 하지 않는다.
    """

    name: ClassVar[str] = "base"
    supported_actions: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def supports_action(cls, action: str) -> bool:
        return action in cls.supported_actions

    @abstractmethod
    def health_check(self) -> SiteHealthStatus:
        """설정/자격증명/세션/브라우저 기동 가능성 수준의 안전한 점검."""

    def login_check(self) -> SiteHealthStatus:
        """로그인 가능 여부의 최소 점검. 기본은 health_check 결과 그대로 재사용."""
        return self.health_check()

    def dry_run(self, task: SiteTask) -> SiteExecutionResult:
        """입력 task 를 요약해서 결과만 반환. 외부 사이트 상태 변경 금지."""
        if not self.supports_action(task.action):
            return SiteExecutionResult(
                task_id=task.task_id,
                target_site=task.target_site,
                action=task.action,
                status="unsupported_action",
                summary=f"{self.name} 는 action={task.action!r} 을 지원하지 않음",
                error_code="UNSUPPORTED_ACTION",
            )
        return SiteExecutionResult(
            task_id=task.task_id,
            target_site=task.target_site,
            action=task.action,
            status="dry_run",
            summary=self._dry_run_summary(task),
        )

    def _dry_run_summary(self, task: SiteTask) -> str:
        """dry_run 요약 문자열. 민감 params 값은 키만 노출."""
        keys = sorted((task.params or {}).keys())
        return f"{self.name} | action={task.action} | mode={task.execution_mode} | param_keys={keys}"

    def execute(self, task: SiteTask) -> SiteExecutionResult:
        """1단계에서는 기본적으로 실행 금지 (NOT_IMPLEMENTED).

        하위 커넥터가 저위험 조회성 action 을 제공할 경우 override 할 수 있다.
        """
        return SiteExecutionResult(
            task_id=task.task_id,
            target_site=task.target_site,
            action=task.action,
            status="not_implemented",
            summary=f"{self.name}.execute 는 1단계에서 비활성",
            error_code="NOT_IMPLEMENTED",
        )


__all__ = ["ConnectorError", "SiteConnector"]
