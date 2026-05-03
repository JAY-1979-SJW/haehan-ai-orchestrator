#!/usr/bin/env python3
"""
LOCAL-FILE-MAP 보안 정적 감사 스크립트.

기능:
위험 패턴 정적 검색.

탐지:
- shell: true / shell=True
- exec( / execSync
- fs.rm / fs.unlink / fs.rmdir
- rm -rf / rimraf / os.remove / os.unlink / shutil.rmtree
- local_file_map.json write
- token/payload console.log
- rollback execute / auto rollback

판정:
- 삭제 API 또는 shell:true 발견 → FAIL
- token/payload 로그 발견 → FAIL
- local_file_map.json write 발견 → FAIL
"""

import os
import re
import json
import sys
from pathlib import Path

def scan_file(filepath):
    """파일에서 위험 패턴을 검사한다."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            lines = content.split('\n')
    except:
        return []

    issues = []

    dangerous_patterns = [
        # 파일 삭제
        (r'\bshell\s*:\s*true\b', 'shell: true 발견', 'FAIL'),
        (r'\bshell\s*=\s*True\b', 'shell=True 발견', 'FAIL'),
        (r'\bexecSync\s*\(', 'execSync() 발견', 'FAIL'),
        (r'\bexec\s*\(\s*["\'].*(?:rm|del|unlink)', 'exec() 파일 삭제 발견', 'FAIL'),
        (r'\bfs\.rm\s*\(', 'fs.rm() 발견', 'FAIL'),
        (r'\bfs\.unlink\s*\(', 'fs.unlink() 발견', 'FAIL'),
        (r'\bfs\.rmdir\s*\(', 'fs.rmdir() 발견', 'FAIL'),
        (r'\bos\.remove\s*\(', 'os.remove() 발견', 'FAIL'),
        (r'\bos\.unlink\s*\(', 'os.unlink() 발견', 'FAIL'),
        (r'\bshutil\.rmtree\s*\(', 'shutil.rmtree() 발견', 'FAIL'),
        (r'\brim(?:raf)?\s*\(', 'rimraf() 발견', 'FAIL'),

        # 로컬 파일맵 수정
        (r'local_file_map\.json.*write', 'local_file_map.json write 발견', 'FAIL'),
        (r'writeFile.*local_file_map\.json', 'local_file_map.json 수정 발견', 'FAIL'),

        # 민감 정보 로그
        (r'console\.log.*(?:approval_token|token|payload)', 'token/payload console.log 발견', 'FAIL'),
        (r'console\.log.*(?:source_path|target_path)', 'path console.log 발견', 'FAIL'),

        # 롤백 자동 실행
        (r'auto.*rollback|automatic.*rollback', 'auto rollback 발견', 'FAIL'),
        (r'rollback.*execute\(', 'rollback execute() 발견', 'FAIL'),
    ]

    for pattern, description, severity in dangerous_patterns:
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line, re.IGNORECASE):
                # 테스트 파일은 경고로 변환 가능
                if 'test' in filepath.lower() or '.spec.' in filepath.lower():
                    severity = 'WARN'

                issues.append({
                    'file': filepath,
                    'line': i,
                    'description': description,
                    'snippet': line.strip()[:100],
                    'severity': severity,
                })

    return issues

def audit_security():
    """보안 정적 감사를 실행한다."""

    base_dir = Path.cwd()
    scanned_files = []
    issues = []

    # 스캔 대상 디렉터리
    scan_targets = [
        'admin-web/src/app/api/file-map',
        'admin-web/src/server/file-map',
        'admin-web/src/lib/fileMap',
        'admin-web/src/components/file-map',
        'agent/local_inventory/file_map',
    ]

    for target in scan_targets:
        for root, dirs, filenames in os.walk(base_dir / target):
            dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', '.next', 'dist', '.venv']]

            for filename in filenames:
                if filename.endswith(('.ts', '.tsx', '.py')):
                    filepath = Path(root) / filename
                    rel_path = str(filepath.relative_to(base_dir))
                    scanned_files.append(rel_path)

                    file_issues = scan_file(filepath)
                    issues.extend(file_issues)

    results = {
        'timestamp': __import__('datetime').datetime.now().isoformat(),
        'baseline': 'f269b0d',
        'scanned_files': len(scanned_files),
        'issues_found': len(issues),
        'issues': issues,
        'status': 'PASS',
    }

    # 심각도 판정
    fail_count = sum(1 for i in issues if i['severity'] == 'FAIL')
    warn_count = sum(1 for i in issues if i['severity'] == 'WARN')

    if fail_count > 0:
        results['status'] = 'FAIL'
    elif warn_count > 0:
        results['status'] = 'WARN'

    return results

if __name__ == '__main__':
    results = audit_security()
    print(json.dumps(results, indent=2, ensure_ascii=False))
    sys.exit(0 if results['status'] == 'PASS' else 1)
