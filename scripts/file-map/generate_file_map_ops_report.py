#!/usr/bin/env python3
"""
LOCAL-FILE-MAP 운영 감사 종합 리포트 생성.

통합:
1. 정적 감사 (modularization, security, component)
2. Smoke 테스트 (fixture dry_run)
3. Audit/Rollback 검증
4. Ops 모니터링
5. 종합 판정
"""

import subprocess
import json
import os
import sys
from pathlib import Path
from datetime import datetime

def run_smoke_test():
    """smoke 테스트 실행."""
    try:
        result = subprocess.run(
            ['python3', 'scripts/file-map/smoke_cleanup_execute_dry_run.py'],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.stdout:
            return json.loads(result.stdout)
    except Exception as e:
        return {'status': 'FAIL', 'error': str(e)}

def verify_audit():
    """audit 검증 실행."""
    try:
        result = subprocess.run(
            ['python3', 'scripts/file-map/verify_audit_rollback.py'],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.stdout:
            return json.loads(result.stdout)
    except Exception as e:
        return {'status': 'FAIL', 'error': str(e)}

def get_monitoring():
    """모니터링 snapshot 실행."""
    try:
        result = subprocess.run(
            ['python3', 'scripts/file-map/ops_monitoring_snapshot.py'],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.stdout:
            return json.loads(result.stdout)
    except Exception as e:
        return {'status': 'FAIL', 'error': str(e)}

def run_static_audits():
    """기존 정적 감사 실행."""
    audits = {}

    # modularization
    try:
        result = subprocess.run(
            ['python3', 'scripts/file-map/audit_modularization.py'],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.stdout:
            audits['modularization'] = json.loads(result.stdout)
    except Exception as e:
        audits['modularization'] = {'status': 'FAIL', 'error': str(e)}

    # security
    try:
        result = subprocess.run(
            ['python3', 'scripts/file-map/audit_security_static.py'],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.stdout:
            audits['security'] = json.loads(result.stdout)
    except Exception as e:
        audits['security'] = {'status': 'FAIL', 'error': str(e)}

    # component
    try:
        result = subprocess.run(
            ['python3', 'scripts/file-map/audit_component_lines.py'],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.stdout:
            audits['component'] = json.loads(result.stdout)
    except Exception as e:
        audits['component'] = {'status': 'FAIL', 'error': str(e)}

    return audits

def determine_overall_status(static, smoke, audit, monitoring):
    """종합 판정."""
    statuses = [
        static.get('modularization', {}).get('status', 'UNKNOWN'),
        static.get('security', {}).get('status', 'UNKNOWN'),
        static.get('component', {}).get('status', 'UNKNOWN'),
        smoke.get('status', 'UNKNOWN'),
        audit.get('status', 'UNKNOWN'),
        monitoring.get('status', 'UNKNOWN'),
    ]

    if 'FAIL' in statuses:
        return 'FAIL'
    elif 'WARN' in statuses:
        return 'WARN'
    else:
        return 'PASS'

if __name__ == '__main__':
    print("🔍 LOCAL-FILE-MAP 운영 감사 수행 중...", file=sys.stderr)

    # 정적 감사
    print("  ✓ 정적 감사 실행...", file=sys.stderr)
    static = run_static_audits()

    # Smoke 테스트
    print("  ✓ Smoke 테스트 실행...", file=sys.stderr)
    smoke = run_smoke_test()

    # Audit 검증
    print("  ✓ Audit/Rollback 검증...", file=sys.stderr)
    audit = verify_audit()

    # Ops 모니터링
    print("  ✓ Ops 모니터링...", file=sys.stderr)
    monitoring = get_monitoring()

    # 종합 판정
    overall = determine_overall_status(static, smoke, audit, monitoring)

    # JSON 리포트
    json_report = {
        'timestamp': datetime.now().isoformat(),
        'baseline': 'HEAD',
        'overall_status': overall,
        'audits': {
            'static': static,
            'smoke': smoke,
            'audit_verification': audit,
            'ops_monitoring': monitoring,
        }
    }

    # Markdown 리포트
    md_report = f"""# LOCAL-FILE-MAP-AUTO-CONTROL-2 운영 감사 보고서

**생성 일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**종합 판정**: {overall}

---

## 감사 결과

| 항목 | 상태 |
|------|------|
| 모듈화 | {static.get('modularization', {}).get('status', 'UNKNOWN')} |
| 보안 | {static.get('security', {}).get('status', 'UNKNOWN')} |
| Component | {static.get('component', {}).get('status', 'UNKNOWN')} |
| Smoke (dry_run) | {smoke.get('status', 'UNKNOWN')} |
| Audit/Rollback | {audit.get('status', 'UNKNOWN')} |
| Ops 모니터링 | {monitoring.get('status', 'UNKNOWN')} |

---

## Smoke 테스트 결과

**상태**: {smoke.get('status', 'UNKNOWN')}

{f"**상세**: {json.dumps(smoke.get('details', {}), ensure_ascii=False)}" if smoke.get('details') else ""}

---

## Audit/Rollback 검증

**상태**: {audit.get('status', 'UNKNOWN')}

- Audit JSONL: {audit.get('audit', {}).get('audit_jsonl_exists', False)}
- Rollback Manifest: {audit.get('audit', {}).get('rollback_manifest_exists', False)}
- 자동 Rollback: {audit.get('audit', {}).get('auto_rollback_executions', 0)}

---

## Ops 모니터링

**건강성**: {monitoring.get('monitoring', {}).get('health_status', 'UNKNOWN')}

- 총 실행: {monitoring.get('monitoring', {}).get('total_executions', 0)}
- dry_run=true: {monitoring.get('monitoring', {}).get('dry_run_true', 0)}
- dry_run=false: {monitoring.get('monitoring', {}).get('dry_run_false', 0)}
- HTTP 500: {monitoring.get('monitoring', {}).get('http_500_count', 0)}

---

**최종 판정**: {overall}
**검증 시점**: {datetime.now().isoformat()}
"""

    # 파일 저장
    reports_dir = Path('docs/reports')
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_path = reports_dir / 'local_file_map_auto_control_2.json'
    md_path = reports_dir / 'local_file_map_auto_control_2.md'

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_report)

    print(f"✓ 리포트 생성 완료", file=sys.stderr)
    print(f"  JSON: {json_path}", file=sys.stderr)
    print(f"  Markdown: {md_path}", file=sys.stderr)
    print(f"  상태: {json_report['overall_status']}", file=sys.stderr)

    sys.exit(0)
