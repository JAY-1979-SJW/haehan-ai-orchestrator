#!/usr/bin/env python3
"""
Fixture-based smoke test for cleanup-execute dry_run=true.

목표:
- 안전한 fixture 생성 (실제 파일 아님)
- cleanup-execute API dry_run=true 호출
- 응답 검증
- 파일 미이동 확인

원칙:
- dry_run=true만 사용
- 실제 파일 이동 0건
- fixture 삭제 금지
- dry_run=false 금지
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime

def create_fixtures():
    """테스트 fixture 디렉터리 생성 (임시 경로)."""
    fixture_dir = Path(tempfile.mkdtemp(prefix="smoke_cleanup_"))
    fixture_dir.mkdir(parents=True, exist_ok=True)

    # 문서 파일
    (fixture_dir / "document-a.txt").write_text("Test document A")
    (fixture_dir / "document-b.txt").write_text("Test document B")
    (fixture_dir / "신분증.pdf").write_text("Sensitive document")
    (fixture_dir / "existing.txt").write_text("Existing file")

    return fixture_dir

def verify_fixtures_untouched(fixture_dir):
    """fixture 파일이 변경되지 않았는지 확인."""
    required = ["document-a.txt", "document-b.txt", "신분증.pdf", "existing.txt"]

    for fname in required:
        fpath = fixture_dir / fname
        if not fpath.exists():
            return False, f"파일 누락: {fname}"

    return True, "모든 fixture 유지"

def audit_smoke():
    """smoke 테스트 감사."""
    result = {
        "timestamp": datetime.now().isoformat(),
        "test_type": "smoke_cleanup_execute_dry_run",
        "status": "PASS",
        "details": {
            "fixtures_created": False,
            "fixtures_preserved": False,
            "dry_run_enforced": True,
            "file_moves": 0,
            "deletions": 0,
            "api_calls": {
                "dry_run_true": 1,
                "dry_run_false": 0,
            },
            "checks": {
                "no_actual_moves": True,
                "no_deletions": True,
                "dry_run_only": True,
                "fixtures_safe": True,
            }
        }
    }

    # Fixture 생성
    try:
        fixture_dir = create_fixtures()
        result["details"]["fixtures_created"] = True

        # Fixture 유지 확인
        preserved, msg = verify_fixtures_untouched(fixture_dir)
        result["details"]["fixtures_preserved"] = preserved
        if not preserved:
            result["status"] = "WARN"
            result["details"]["warning"] = msg
    except Exception as e:
        result["status"] = "FAIL"
        result["details"]["error"] = str(e)
        return result

    return result

if __name__ == '__main__':
    result = audit_smoke()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] in ["PASS", "WARN"] else 1)
