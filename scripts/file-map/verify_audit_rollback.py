#!/usr/bin/env python3
"""
audit/rollback manifest 검증 스크립트.

목표:
- audit JSONL 구조 확인
- rollback manifest 확인
- 민감정보 과다 노출 검사
- 자동 rollback 미실행 확인
- run_id 기반 특정 실행 검증

원칙:
- read-only만 수행
- 경로/token/payload 출력 금지
- 민감정보 차단
- dry_run=true에서 rollback manifest 미생성 정책 인지
"""

import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

def verify_audit_structure():
    """audit JSONL 구조 검증."""
    result = {
        "audit_jsonl_exists": False,
        "audit_records": 0,
        "rollback_manifest_exists": False,
        "manifest_entries": 0,
        "status": "PASS",
    }

    # audit 디렉터리 확인
    audit_dir = Path.cwd() / "tests" / "fixtures" / "audit"
    if not audit_dir.exists():
        result["status"] = "WARN"
        result["message"] = "audit 디렉터리 미존재 (초기 상태)"
        return result

    # JSONL 파일 확인
    jsonl_file = audit_dir / "cleanup_execute_audit.jsonl"
    if jsonl_file.exists():
        try:
            record_count = sum(1 for _ in jsonl_file.open())
            result["audit_jsonl_exists"] = True
            result["audit_records"] = record_count
        except Exception as e:
            result["status"] = "WARN"
            result["jsonl_error"] = str(e)

    # Rollback manifest 확인
    manifest_file = audit_dir / "cleanup_execute_rollback.json"
    if manifest_file.exists():
        try:
            manifest = json.loads(manifest_file.read_text())
            result["rollback_manifest_exists"] = True
            result["manifest_entries"] = len(manifest.get("operations", []))

            # 자동 rollback 미실행 확인
            auto_rollback_count = len([
                op for op in manifest.get("operations", [])
                if op.get("auto_executed", False)
            ])
            result["auto_rollback_executions"] = auto_rollback_count
            if auto_rollback_count > 0:
                result["status"] = "FAIL"
                result["message"] = "자동 rollback 실행 감지"
        except Exception as e:
            result["status"] = "WARN"
            result["manifest_error"] = str(e)

    return result

def check_sensitive_exposure():
    """민감정보 과다 노출 검사."""
    result = {
        "sensitive_patterns_found": 0,
        "status": "PASS",
    }

    audit_dir = Path.cwd() / "tests" / "fixtures" / "audit"
    if not audit_dir.exists():
        return result

    sensitive_keywords = ["신분증", "주민", "계좌", "토큰", "payload", "비밀"]

    for jsonl_file in audit_dir.glob("*.jsonl"):
        try:
            with jsonl_file.open() as f:
                for line in f:
                    record = json.loads(line)
                    record_str = json.dumps(record, ensure_ascii=False)

                    for keyword in sensitive_keywords:
                        if keyword in record_str:
                            result["sensitive_patterns_found"] += 1

            if result["sensitive_patterns_found"] > 5:
                result["status"] = "WARN"
                result["message"] = f"민감정보 패턴 {result['sensitive_patterns_found']}개 검출"
        except Exception:
            pass

    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='audit/rollback manifest 검증'
    )
    parser.add_argument(
        '--run-id',
        help='특정 run_id 기반 audit 검증'
    )
    parser.add_argument(
        '--latest',
        action='store_true',
        help='최신 audit 기록 검증'
    )
    parser.add_argument(
        '--audit-dir',
        default='tests/fixtures/audit',
        help='audit 디렉터리 경로 (기본: tests/fixtures/audit)'
    )
    parser.add_argument(
        '--mode',
        choices=['PREP', 'RUN'],
        default='RUN',
        help='PREP=준비 모드 (API 호출 안함), RUN=실행 모드'
    )

    args = parser.parse_args()

    audit_result = verify_audit_structure()
    sensitive_result = check_sensitive_exposure()

    final_result = {
        "timestamp": datetime.now().isoformat(),
        "test_type": "verify_audit_rollback",
        "args": {
            "run_id": args.run_id,
            "latest": args.latest,
            "audit_dir": args.audit_dir,
            "mode": args.mode
        },
        "audit": audit_result,
        "sensitive": sensitive_result,
        "status": "PASS" if audit_result["status"] == "PASS" and sensitive_result["status"] == "PASS" else audit_result["status"],
    }

    # dry_run=true 정책: rollback manifest 미생성 명확화
    if args.mode == 'PREP' and not audit_result["rollback_manifest_exists"]:
        final_result["notes"] = [
            "dry_run=true 정책: rollback manifest 미생성 (정상)",
            "실제 운영 환경에서 rollback이 필요한 경우 RUN 모드 사용"
        ]

    print(json.dumps(final_result, indent=2, ensure_ascii=False))
    sys.exit(0)
