#!/usr/bin/env python3
"""
Component line count 감사 스크립트.

기능:
- component별 line count
- 350줄 초과 탐지
- file-map component 총량 집계
- 상위 10개 큰 component 출력

판정:
- 350줄 초과 있음 → WARN 또는 FAIL
- 400줄 초과 있음 → FAIL
- 모든 component 350줄 이하 → PASS
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

def audit_component_lines():
    """component line count 감사를 실행한다."""

    base_dir = Path.cwd()
    components = []
    total_lines = 0

    # React component 파일 찾기
    component_dir = base_dir / 'admin-web/src/components/file-map'

    if component_dir.exists():
        for root, dirs, filenames in os.walk(component_dir):
            for filename in filenames:
                if filename.endswith('.tsx'):
                    filepath = Path(root) / filename
                    rel_path = str(filepath.relative_to(base_dir))
                    lines = count_lines(filepath)

                    components.append({
                        'file': rel_path,
                        'lines': lines,
                        'exceeds_350': lines > 350,
                        'exceeds_400': lines > 400,
                    })

                    total_lines += lines

    # 크기순 정렬
    components_sorted = sorted(components, key=lambda x: x['lines'], reverse=True)

    # 상위 10개
    top_10 = components_sorted[:10]

    # 판정
    exceeds_400 = sum(1 for c in components if c['exceeds_400'])
    exceeds_350 = sum(1 for c in components if c['exceeds_350'])

    status = 'PASS'
    if exceeds_400 > 0:
        status = 'FAIL'
    elif exceeds_350 > 0:
        status = 'WARN'

    results = {
        'timestamp': __import__('datetime').datetime.now().isoformat(),
        'baseline': 'f269b0d',
        'summary': {
            'total_components': len(components),
            'total_lines': total_lines,
            'avg_lines': total_lines // len(components) if components else 0,
            'exceeds_400': exceeds_400,
            'exceeds_350': exceeds_350,
        },
        'top_10_largest': top_10,
        'all_components': components_sorted,
        'status': status,
    }

    return results

if __name__ == '__main__':
    results = audit_component_lines()
    print(json.dumps(results, indent=2, ensure_ascii=False))
    sys.exit(0 if results['status'] == 'PASS' else 1)
