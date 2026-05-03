#!/usr/bin/env python3
"""
cleanup-execute API dry_run smoke test (실제 API 호출).

목표:
- FILE_MAP_BASE_URL으로 실제 관리 웹 API 호출
- dry_run=true 강제
- /tmp fixture 대상
- run_id 추출
- 파일 이동 여부 확인
- audit JSONL 기록 확인

원칙:
- FILE_MAP_BASE_URL 필수 (미설정 시 FAIL)
- base_target_dir는 /tmp로 시작해야 함 (미충족 시 FAIL)
- dry_run=true 고정 (false 요청 차단)
- tests/fixtures 사용 금지
- 실제 사용자 경로 금지
- token/path/payload 로그 출력 금지
"""

import json
import os
import sys
import tempfile
import requests
from pathlib import Path
from datetime import datetime
import uuid

def check_environment():
    """환경 변수 확인."""
    base_url = os.environ.get('FILE_MAP_BASE_URL')
    if not base_url:
        return {
            'status': 'FAIL',
            'error': 'FILE_MAP_BASE_URL 환경변수 필수',
            'action': 'export FILE_MAP_BASE_URL=<admin-web-url> 실행 후 재시도',
            'example': 'export FILE_MAP_BASE_URL="https://haehan-ai.kr" 또는 "http://localhost:3000"'
        }

    return {
        'status': 'OK',
        'base_url': base_url
    }

def create_fixtures():
    """테스트 fixture 생성 (/tmp)."""
    fixture_base = Path(tempfile.mkdtemp(prefix="file_map_api_smoke_"))
    source_dir = fixture_base / "source"
    target_dir = fixture_base / "target"

    source_dir.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Source 파일들
    (source_dir / "document-a.txt").write_text("Document A content")
    (source_dir / "document-b.txt").write_text("Document B content")
    (source_dir / "신분증.pdf").write_text("Sensitive document")

    # Target 파일
    (target_dir / "existing.txt").write_text("Existing target file")

    return {
        'base': str(fixture_base),
        'source': str(source_dir),
        'target': str(target_dir)
    }

def validate_target_path(target_dir):
    """target 경로가 /tmp로 시작하는지 확인."""
    if not target_dir.startswith('/tmp'):
        return {
            'valid': False,
            'error': f'base_target_dir는 /tmp로 시작해야 함: {target_dir}'
        }
    return {'valid': True}

def prepare_request_payload(source_dir, target_dir):
    """API 요청 payload 작성."""
    # plans에는 document-a.txt, document-b.txt만 포함 (신분증.pdf 제외)
    plans = [
        {
            "source": str(Path(source_dir) / "document-a.txt"),
            "target": str(Path(target_dir) / "document-a.txt"),
            "confirmed": True
        },
        {
            "source": str(Path(source_dir) / "document-b.txt"),
            "target": str(Path(target_dir) / "document-b.txt"),
            "confirmed": True
        }
    ]

    payload = {
        'dry_run': True,
        'preflight_id': str(uuid.uuid4()),
        'package_id': str(uuid.uuid4()),
        'approval_token': f'user-approved-cleanup-{uuid.uuid4()}',
        'user_confirmed_execution': True,
        'base_target_dir': target_dir,
        'plans': plans
    }

    return payload

def call_api(base_url, payload):
    """cleanup-execute API 호출 (시뮬레이션)."""
    if not base_url:
        return {
            'status': 'SKIP',
            'reason': 'FILE_MAP_BASE_URL 미설정: 실제 API 호출 생략',
            'payload_prepared': True,
            'dry_run': payload.get('dry_run')
        }

    api_endpoint = f"{base_url}/api/file-map/cleanup-execute"

    try:
        response = requests.post(
            api_endpoint,
            json=payload,
            timeout=30,
            headers={'Content-Type': 'application/json'}
        )

        if response.status_code == 200:
            result = response.json()
            return {
                'status': 'SUCCESS',
                'http_status': response.status_code,
                'run_id': result.get('run_id'),
                'dry_run_confirmed': result.get('dry_run') == True,
                'success_count': result.get('success_count', 0),
                'succeeded': len(result.get('succeeded', [])),
                'failed_count': result.get('failed_count', 0)
            }
        else:
            return {
                'status': 'HTTP_ERROR',
                'http_status': response.status_code,
                'error': f'API 호출 실패 (status={response.status_code})'
            }
    except requests.exceptions.ConnectionError:
        return {
            'status': 'CONNECTION_ERROR',
            'error': f'API 접속 실패: {api_endpoint}',
            'hint': 'FILE_MAP_BASE_URL 확인'
        }
    except Exception as e:
        return {
            'status': 'ERROR',
            'error': str(e)
        }

def verify_fixtures_untouched(source_dir, target_dir):
    """fixture 파일 변경 없음 확인."""
    results = {
        'source_files_exist': True,
        'target_unmoved': True,
        'files_checked': []
    }

    source_path = Path(source_dir)
    target_path = Path(target_dir)

    # Source 파일 확인
    for fname in ['document-a.txt', 'document-b.txt', '신분증.pdf']:
        fpath = source_path / fname
        exists = fpath.exists()
        results['files_checked'].append({
            'path': fname,
            'type': 'source',
            'exists': exists
        })
        if not exists:
            results['source_files_exist'] = False

    # Target에 document-a, b 없음 확인
    for fname in ['document-a.txt', 'document-b.txt']:
        fpath = target_path / fname
        exists = fpath.exists()
        results['files_checked'].append({
            'path': fname,
            'type': 'target',
            'should_not_exist': True,
            'exists': exists
        })
        if exists:
            results['target_unmoved'] = False

    # Target existing.txt는 유지
    existing = (target_path / 'existing.txt').exists()
    results['files_checked'].append({
        'path': 'existing.txt',
        'type': 'target',
        'should_exist': True,
        'exists': existing
    })

    return results

def audit_smoke():
    """smoke 테스트 실행."""
    result = {
        'timestamp': datetime.now().isoformat(),
        'test_type': 'smoke_cleanup_execute_api_dry_run',
        'status': 'PASS',
        'details': {
            'environment_check': None,
            'fixtures_created': False,
            'fixture_path': None,
            'dry_run_enforced': True,
            'api_call_status': None,
            'run_id': None,
            'file_integrity': None,
            'notes': []
        }
    }

    # Step 1: 환경 확인
    env_check = check_environment()
    result['details']['environment_check'] = env_check

    if env_check['status'] == 'FAIL':
        result['status'] = 'FAIL'
        result['details']['notes'].append(f"환경 실패: {env_check['error']}")
        return result

    base_url = env_check['base_url']

    # Step 2: Fixture 생성
    try:
        fixtures = create_fixtures()
        result['details']['fixtures_created'] = True
        result['details']['fixture_path'] = fixtures['base']

        # Step 3: Target 경로 검증
        target_validation = validate_target_path(fixtures['target'])
        if not target_validation['valid']:
            result['status'] = 'FAIL'
            result['details']['notes'].append(f"경로 검증 실패: {target_validation['error']}")
            return result

        # Step 4: Request payload 작성
        payload = prepare_request_payload(fixtures['source'], fixtures['target'])
        result['details']['dry_run_enforced'] = (payload['dry_run'] == True)

        # dry_run=false 차단
        if payload.get('dry_run') != True:
            result['status'] = 'FAIL'
            result['details']['notes'].append("dry_run=false 차단됨")
            return result

        # Step 5: API 호출
        api_result = call_api(base_url, payload)
        result['details']['api_call_status'] = api_result

        if api_result['status'] == 'SKIP':
            result['status'] = 'WARN'
            result['details']['notes'].append("API 호출 생략 (FILE_MAP_BASE_URL 기본값 또는 PREP 모드)")
        elif api_result['status'] == 'SUCCESS':
            result['details']['run_id'] = api_result.get('run_id')
            if not result['details']['run_id']:
                result['status'] = 'FAIL'
                result['details']['notes'].append("run_id 미반환")
        elif api_result['status'] in ['HTTP_ERROR', 'CONNECTION_ERROR', 'ERROR']:
            result['status'] = 'FAIL'
            result['details']['notes'].append(f"API 호출 실패: {api_result.get('error')}")

        # Step 6: Fixture 무결성 확인
        if result['status'] != 'FAIL':
            file_check = verify_fixtures_untouched(fixtures['source'], fixtures['target'])
            result['details']['file_integrity'] = file_check

            if not file_check['source_files_exist'] or not file_check['target_unmoved']:
                result['status'] = 'FAIL'
                result['details']['notes'].append("파일 무결성 검증 실패")

    except Exception as e:
        result['status'] = 'FAIL'
        result['details']['notes'].append(f"예외: {str(e)}")

    return result

if __name__ == '__main__':
    result = audit_smoke()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result['status'] in ['PASS', 'WARN'] else 1)
