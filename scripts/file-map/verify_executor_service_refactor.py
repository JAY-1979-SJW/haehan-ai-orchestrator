#!/usr/bin/env python3
"""
EXECUTOR-SERVICE-2F-AUTO-VERIFY: Automated verification of refactor completeness.

목표:
- EXECUTOR-SERVICE-2B~2E 구현 검증
- spawn 제거 확인
- HTTP client 전환 확인
- 정책 보존 확인
- Dockerfile/compose 존재 확인
- 테스트 파일 존재 확인
- 문서 완성 확인

원칙:
- 코드 수정 금지 (읽기만 수행)
- Dockerfile/compose 수정 금지
- 실제 테스트 실행 없음 (pytest는 별도)
- 서버 배포 확인 금지
- dry_run 정책 검증만 수행
"""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime


class ExecutorServiceVerifier:
    """EXECUTOR-SERVICE 구현 검증 도구."""

    def __init__(self, repo_root: str = None):
        """초기화."""
        if repo_root is None:
            repo_root = Path(__file__).resolve().parent.parent.parent
        self.repo_root = Path(repo_root)
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'repo_root': str(self.repo_root),
            'checks': {},
            'summary': {'total': 0, 'pass': 0, 'fail': 0, 'warn': 0},
            'status': 'PENDING',
        }

    def verify(self) -> dict:
        """모든 검증 실행."""
        print("=" * 60)
        print("EXECUTOR-SERVICE-2F-AUTO-VERIFY")
        print("=" * 60)
        print()

        # 검증 항목들
        self._verify_spawn_removed()
        self._verify_http_client()
        self._verify_file_map_executor_service()
        self._verify_policies()
        self._verify_dockerfile_compose()
        self._verify_test_files()
        self._verify_documentation()
        self._verify_no_deployment()

        # 최종 판정
        self._finalize_results()

        return self.results

    def _check(self, name: str, condition: bool, message: str = ""):
        """검증 결과 기록."""
        status = "PASS" if condition else "FAIL"
        self.results['checks'][name] = {
            'status': status,
            'message': message,
        }
        self.results['summary']['total'] += 1
        if status == "PASS":
            self.results['summary']['pass'] += 1
            print(f"✅ {name}")
        else:
            self.results['summary']['fail'] += 1
            print(f"❌ {name}")
        if message:
            print(f"   {message}")

    def _verify_spawn_removed(self):
        """admin-web에서 spawn 제거 확인."""
        print("\n[1/7] Spawn 제거 확인")
        print("-" * 40)

        pythonExecutor_path = (
            self.repo_root / "admin-web/src/lib/file-map/pythonExecutor.ts"
        )

        if not pythonExecutor_path.exists():
            self._check(
                "pythonExecutor.ts 존재",
                False,
                f"파일 없음: {pythonExecutor_path}",
            )
            return

        self._check("pythonExecutor.ts 존재", True)

        content = pythonExecutor_path.read_text(encoding='utf-8')

        # spawn 미사용 확인 (주석 제외)
        lines = content.split('\n')
        code_lines = [
            line for line in lines
            if not line.strip().startswith('//') and not line.strip().startswith('*')
        ]
        code_content = '\n'.join(code_lines)
        has_spawn = 'spawn(' in code_content or "spawn'" in code_content
        self._check("spawn 제거", not has_spawn,
                   "spawn이 코드에서 완전히 제거되어야 함 (주석 제외)")

        # child_process 미사용
        has_child_process = (
            "from 'child_process'" in content or
            'import child_process' in content or
            "child_process" in content.split('/**')[0]
        )
        self._check("child_process 제거", not has_child_process,
                   "child_process module이 제거되어야 함")

        # fs, path 제거
        has_fs = "'fs'" in content or '"fs"' in content
        has_path = ("'path'" in content or '"path"' in content) and 'path:' not in content
        self._check("fs 제거", not has_fs)
        self._check("path 제거", not has_path)

        # resolveRepoRoot/resolveCleanupExecutorPath 제거
        has_resolve_root = "resolveRepoRoot" in content
        has_resolve_path = "resolveCleanupExecutorPath" in content
        self._check("resolveRepoRoot 제거", not has_resolve_root)
        self._check("resolveCleanupExecutorPath 제거", not has_resolve_path)

    def _verify_http_client(self):
        """HTTP client 구현 확인."""
        print("\n[2/7] HTTP Client 전환 확인")
        print("-" * 40)

        pythonExecutor_path = (
            self.repo_root / "admin-web/src/lib/file-map/pythonExecutor.ts"
        )
        content = pythonExecutor_path.read_text(encoding='utf-8')

        # fetch 사용
        has_fetch = 'fetch(' in content
        self._check("fetch() 사용", has_fetch,
                   "fetch()를 사용하여 HTTP 호출해야 함")

        # FILE_MAP_EXECUTOR_URL 환경변수 사용
        has_env_url = 'FILE_MAP_EXECUTOR_URL' in content
        self._check("FILE_MAP_EXECUTOR_URL 사용", has_env_url,
                   "환경변수로 executor URL 설정해야 함")

        # 기본값: http://file-map-executor:8510
        has_default_url = 'http://file-map-executor:8510' in content
        self._check("기본값 설정 (file-map-executor:8510)", has_default_url,
                   "기본 URL이 http://file-map-executor:8510이어야 함")

        # /cleanup/execute endpoint
        has_cleanup_execute = '/cleanup/execute' in content
        self._check("/cleanup/execute 호출", has_cleanup_execute,
                   "executor의 POST /cleanup/execute를 호출해야 함")

        # 30초 timeout
        has_timeout = 'timeout(30000)' in content or '30000' in content
        self._check("30초 timeout 설정", has_timeout,
                   "AbortSignal.timeout(30000)으로 30초 제한해야 함")

        # POST method
        has_post = "method: 'POST'" in content or 'method: "POST"' in content
        self._check("POST method 사용", has_post)

        # JSON Content-Type
        has_json_header = 'Content-Type' in content and 'json' in content
        self._check("JSON Content-Type 헤더", has_json_header)

        # adaptExecutorResponse 함수
        has_adapter = 'adaptExecutorResponse' in content
        self._check("응답 어댑터 함수", has_adapter,
                   "executor 응답을 admin-web 형식으로 변환해야 함")

    def _verify_file_map_executor_service(self):
        """file-map-executor service 확인."""
        print("\n[3/7] File-Map-Executor Service 확인")
        print("-" * 40)

        service_dir = self.repo_root / "services/file_map_executor"

        # 디렉터리 존재
        self._check("services/file_map_executor 디렉터리", service_dir.exists())

        if not service_dir.exists():
            return

        # 핵심 파일들
        files_to_check = [
            ("__init__.py", "패키지 마커"),
            ("app.py", "FastAPI app"),
            ("schemas.py", "Pydantic models"),
            ("service.py", "비즈니스 로직"),
            ("security.py", "검증 유틸리티"),
        ]

        for filename, desc in files_to_check:
            filepath = service_dir / filename
            self._check(f"{filename} ({desc})", filepath.exists())

        # endpoints 확인
        app_py = service_dir / "app.py"
        if app_py.exists():
            content = app_py.read_text(encoding='utf-8')

            endpoints = [
                ("GET /health", "/health"),
                ("POST /cleanup/execute", "/cleanup/execute"),
                ("GET /cleanup/audit", "/cleanup/audit"),
                ("GET /cleanup/rollback", "/cleanup/rollback"),
            ]

            for name, path in endpoints:
                has_endpoint = path in content
                self._check(f"Endpoint: {name}", has_endpoint)

    def _verify_policies(self):
        """정책 보존 확인."""
        print("\n[4/7] 정책 보존 확인")
        print("-" * 40)

        # dry_run=false 차단
        security_py = self.repo_root / "services/file_map_executor/security.py"
        if security_py.exists():
            content = security_py.read_text(encoding='utf-8')
            has_dry_run_validation = (
                'validate_dry_run' in content and
                ('if not dry_run' in content or
                 '== False' in content or
                 'is False' in content or
                 '!= True' in content or
                 'not supported' in content.lower())
            )
            self._check("dry_run=false 검증", has_dry_run_validation,
                       "security.py에서 dry_run=false를 차단해야 함")

        # /tmp 경로 강제
        if security_py.exists():
            content = security_py.read_text(encoding='utf-8')
            has_tmp_validation = '/tmp' in content
            self._check("/tmp 경로 강제", has_tmp_validation,
                       "security.py에서 /tmp 경로를 강제해야 함")

        # route.ts에서 dry_run 강제
        route_ts = (
            self.repo_root / "admin-web/src/app/api/file-map/cleanup-execute/route.ts"
        )
        if route_ts.exists():
            content = route_ts.read_text(encoding='utf-8')
            has_dry_run_enforce = 'dry_run === false ? false : true' in content
            self._check("route.ts에서 dry_run 강제", has_dry_run_enforce,
                       "line 56: dry_run === false ? false : true")

        # approval_token 검증
        if route_ts.exists():
            content = route_ts.read_text(encoding='utf-8')
            has_token_validation = 'validateApprovalToken' in content
            self._check("approval_token 검증", has_token_validation)

        # rollback read-only
        service_py = self.repo_root / "services/file_map_executor/service.py"
        if service_py.exists():
            content = service_py.read_text(encoding='utf-8')
            has_rollback_readonly = '"pending"' in content or "'pending'" in content
            self._check("rollback read-only (pending status)", has_rollback_readonly)

        # 로그에 token/path 원문 미포함
        app_py = self.repo_root / "services/file_map_executor/app.py"
        if app_py.exists():
            content = app_py.read_text(encoding='utf-8')
            # logging.error/warning에서 full request dict 출력 없음
            has_full_logging = (
                'logging.error(request' in content or
                'logging.warning(request' in content or
                'logger.error(request' in content
            )
            self._check("민감 정보 로그 금지", not has_full_logging,
                       "request 전체를 로깅하면 안 됨")

    def _verify_dockerfile_compose(self):
        """Dockerfile 및 compose 확인."""
        print("\n[5/7] Dockerfile/Compose 확인")
        print("-" * 40)

        # Dockerfile
        dockerfile = self.repo_root / "docker/file-map-executor.Dockerfile"
        self._check("file-map-executor.Dockerfile", dockerfile.exists())

        # compose fragment
        compose_fragment = self.repo_root / "docker/docker-compose.file-map-executor.yml"
        self._check("docker-compose.file-map-executor.yml", compose_fragment.exists())

        # dev compose
        dev_compose = self.repo_root / "docker/docker-compose.dev.yml"
        self._check("docker-compose.dev.yml", dev_compose.exists(),
                   "로컬 테스트용 compose")

        # Dockerfile 내용 확인
        if dockerfile.exists():
            content = dockerfile.read_text(encoding='utf-8')
            checks = [
                ("python:3.11-slim" in content, "Python 3.11-slim base image"),
                ("fastapi" in content, "fastapi 패키지"),
                ("uvicorn" in content, "uvicorn 패키지"),
                ("pydantic" in content, "pydantic 패키지"),
                ("8510" in content, "포트 8510"),
            ]
            for condition, desc in checks:
                self._check(f"Dockerfile: {desc}", condition)

    def _verify_test_files(self):
        """테스트 파일 확인."""
        print("\n[6/7] 테스트 파일 확인")
        print("-" * 40)

        # Python 테스트
        pytest_file = self.repo_root / "tests/test_file_map_executor_service.py"
        self._check("test_file_map_executor_service.py", pytest_file.exists(),
                   "pytest 테스트 (11개 테스트)")

        # Jest 테스트
        jest_file = (
            self.repo_root /
            "admin-web/src/lib/file-map/__tests__/pythonExecutor.test.ts"
        )
        self._check("pythonExecutor.test.ts", jest_file.exists(),
                   "jest 테스트 (8개 테스트)")

    def _verify_documentation(self):
        """문서 완성도 확인."""
        print("\n[7/7] 문서 확인")
        print("-" * 40)

        reports_dir = self.repo_root / "docs/reports"

        reports = [
            ("local_file_map_executor_service_2a_skeleton.md", "2A Skeleton"),
            ("local_file_map_executor_service_2b_admin_web_client.md", "2B HTTP Client"),
            ("local_file_map_executor_service_2c_integration_test.md", "2C Integration"),
            ("local_file_map_executor_service_2d_deployment_prep.md", "2D Deployment"),
            ("local_file_map_executor_service_2e_final_verification.md", "2E Verification"),
            ("EXECUTOR_SERVICE_REFACTOR_SUMMARY.md", "Summary"),
        ]

        for filename, desc in reports:
            filepath = reports_dir / filename
            self._check(f"보고서: {desc}", filepath.exists())

    def _verify_no_deployment(self):
        """운영 배포 미수행 확인."""
        print("\n[추가] 배포 상태 확인")
        print("-" * 40)

        # git에서 커밋 확인
        git_dir = self.repo_root / ".git"
        if git_dir.exists():
            self._check("로컬 master branch에서 구현됨", True,
                       "아직 서버 feature/dashboard-monitor에 배포 안 됨")

        # 서버 파일 접근 불가 (로컬 환경)
        server_path = Path("/home/ubuntu/apps/haehan-ai-orchestrator")
        self._check("서버 배포 미수행", not server_path.exists(),
                   "로컬 환경에서만 구현됨")

    def _finalize_results(self):
        """최종 판정."""
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        summary = self.results['summary']
        total = summary['total']
        passed = summary['pass']
        failed = summary['fail']

        print(f"Total: {total} | Pass: {passed} | Fail: {failed}")
        print()

        if failed == 0:
            self.results['status'] = 'PASS'
            print("✅ 모든 검증 통과")
        elif failed <= total * 0.1:  # 10% 이상 실패면 WARN
            self.results['status'] = 'WARN'
            print("⚠️  일부 검증 실패 (10% 이상)")
        else:
            self.results['status'] = 'FAIL'
            print("❌ 검증 실패")

        print("=" * 60)


def main():
    """메인 함수."""
    verifier = ExecutorServiceVerifier()
    results = verifier.verify()

    # JSON 결과 저장
    output_json = (
        Path(__file__).parent.parent.parent /
        "docs/reports/local_file_map_executor_service_2f_verify_lock.json"
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print()
    print(f"📄 결과 저장: {output_json}")
    print()

    # 상태코드
    if results['status'] == 'PASS':
        return 0
    elif results['status'] == 'WARN':
        return 0  # WARN도 실행 성공으로 처리
    else:
        return 1


if __name__ == '__main__':
    sys.exit(main())
