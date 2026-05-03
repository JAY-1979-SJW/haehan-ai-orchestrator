#!/usr/bin/env python3
"""
LOCAL-FILE-MAP 모듈화 감사 스크립트.

기능:
- file-map 관련 route/lib/component/Python 파일 line count 집계
- 기준 초과 자동 판정

기준:
- API route: 150줄 이하 권장
- client lib: 200줄 이하 권장
- React component: 350줄 이하
- Python module: 350줄 이하
- server helper: 250줄 이하 권장

출력:
- JSON summary
- PASS/WARN/FAIL
"""

import os
import json
import sys
from pathlib import Path

def count_lines(filepath):
    """파일의 줄 수를 센다."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return len(f.readlines())
    except:
        return 0

def find_files(pattern):
    """주어진 패턴의 파일들을 찾는다."""
    files = []
    base_dir = Path.cwd()

    for root, dirs, filenames in os.walk(base_dir):
        # 무시할 디렉터리
        dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', '.next', 'dist', '.venv']]

        for filename in filenames:
            filepath = Path(root) / filename
            rel_path = filepath.relative_to(base_dir)

            # 패턴 매칭
            if str(rel_path).replace('\\', '/').startswith(pattern.replace('\\', '/')):
                if filename.endswith(('.ts', '.tsx', '.py')):
                    files.append(str(rel_path))

    return sorted(files)

def audit_modularization():
    """모듈화 감사를 실행한다."""

    # 대상 디렉터리 목록
    targets = {
        'API Routes': {
            'pattern': 'admin-web/src/app/api/file-map',
            'max_lines': 150,
            'severity': 'warn',
        },
        'Server Lib': {
            'pattern': 'admin-web/src/server/file-map',
            'max_lines': 250,
            'severity': 'warn',
        },
        'Client Lib': {
            'pattern': 'admin-web/src/lib/fileMap',
            'max_lines': 200,
            'severity': 'warn',
        },
        'React Components': {
            'pattern': 'admin-web/src/components/file-map',
            'max_lines': 350,
            'severity': 'warn',
        },
        'Python Modules': {
            'pattern': 'agent/local_inventory/file_map',
            'max_lines': 350,
            'severity': 'warn',
        },
    }

    results = {
        'timestamp': __import__('datetime').datetime.now().isoformat(),
        'baseline': 'f269b0d',
        'categories': {},
        'summary': {
            'total_files': 0,
            'total_lines': 0,
            'exceeds_max': 0,
        },
        'exceeding_files': [],
        'status': 'PASS',
    }

    for category, config in targets.items():
        files = find_files(config['pattern'])

        if not files:
            results['categories'][category] = {
                'files': [],
                'total': 0,
            }
            continue

        category_files = []
        category_lines = 0
        exceeds = 0

        for filepath in files:
            lines = count_lines(filepath)
            category_files.append({
                'file': filepath,
                'lines': lines,
                'exceeds': lines > config['max_lines'],
            })
            category_lines += lines

            if lines > config['max_lines']:
                exceeds += 1
                results['exceeding_files'].append({
                    'category': category,
                    'file': filepath,
                    'lines': lines,
                    'max': config['max_lines'],
                    'excess': lines - config['max_lines'],
                })

                if config['severity'] == 'fail':
                    results['status'] = 'FAIL'
                elif results['status'] != 'FAIL':
                    results['status'] = 'WARN'

        results['categories'][category] = {
            'files': category_files,
            'total_files': len(files),
            'total_lines': category_lines,
            'exceeds_max': exceeds,
            'max_per_file': config['max_lines'],
        }

        results['summary']['total_files'] += len(files)
        results['summary']['total_lines'] += category_lines
        results['summary']['exceeds_max'] += exceeds

    return results

if __name__ == '__main__':
    results = audit_modularization()
    print(json.dumps(results, indent=2, ensure_ascii=False))
    sys.exit(0 if results['status'] == 'PASS' else 1)
