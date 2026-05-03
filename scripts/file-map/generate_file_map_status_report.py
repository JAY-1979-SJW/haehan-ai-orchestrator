#!/usr/bin/env python3
"""
LOCAL-FILE-MAP 자동 제어 상태 보고서 생성 스크립트.

기능:
위 3개 감사 스크립트 결과를 종합해 보고서 생성.

출력:
- docs/reports/local_file_map_auto_control_1.md
- docs/reports/local_file_map_auto_control_1.json
"""

import subprocess
import json
import os
import sys
from pathlib import Path
from datetime import datetime

def run_script(script_name):
    """감사 스크립트를 실행하고 결과를 반환한다."""
    script_path = Path.cwd() / 'scripts/file-map' / f'{script_name}.py'

    try:
        result = subprocess.run(
            ['python3', str(script_path)],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.stdout:
            return json.loads(result.stdout)
        else:
            return {'error': result.stderr}
    except Exception as e:
        return {'error': str(e)}

def generate_report():
    """모든 감사 스크립트를 실행하고 보고서를 생성한다."""

    print("🔍 감사 스크립트 실행 중...", file=sys.stderr)

    # 감사 스크립트 실행
    mod_results = run_script('audit_modularization')
    sec_results = run_script('audit_security_static')
    comp_results = run_script('audit_component_lines')

    print(f"  ✓ 모듈화 감사: {mod_results.get('status', 'ERROR')}", file=sys.stderr)
    print(f"  ✓ 보안 감사: {sec_results.get('status', 'ERROR')}", file=sys.stderr)
    print(f"  ✓ Component 감사: {comp_results.get('status', 'ERROR')}", file=sys.stderr)

    # 종합 판정
    statuses = [
        mod_results.get('status', 'FAIL'),
        sec_results.get('status', 'FAIL'),
        comp_results.get('status', 'FAIL'),
    ]

    if 'FAIL' in statuses:
        overall_status = 'FAIL'
    elif 'WARN' in statuses:
        overall_status = 'WARN'
    else:
        overall_status = 'PASS'

    # JSON 보고서
    json_report = {
        'timestamp': datetime.now().isoformat(),
        'baseline': 'f269b0d',
        'overall_status': overall_status,
        'audits': {
            'modularization': mod_results,
            'security': sec_results,
            'component_lines': comp_results,
        },
    }

    # Markdown 보고서
    md_report = f"""# LOCAL-FILE-MAP-AUTO-CONTROL-1 자동 제어 상태 보고서

**생성 일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**기준선**: f269b0d
**종합 판정**: {overall_status}

---

## 감사 결과 요약

| 감사 항목 | 상태 | 세부 |
|---------|------|------|
| 모듈화 | {mod_results.get('status', 'ERROR')} | {mod_results.get('summary', {}).get('exceeds_max', 0)}개 파일 초과 |
| 보안 | {sec_results.get('status', 'ERROR')} | {sec_results.get('issues_found', 0)}개 이슈 발견 |
| Component | {comp_results.get('status', 'ERROR')} | 350줄 초과 {comp_results.get('summary', {}).get('exceeds_350', 0)}개 |

---

## 모듈화 감사

### 상태: {mod_results.get('status', 'ERROR')}

**집계**:
- 총 파일 수: {mod_results.get('summary', {}).get('total_files', 0)}
- 총 라인 수: {mod_results.get('summary', {}).get('total_lines', 0)}
- 기준 초과: {mod_results.get('summary', {}).get('exceeds_max', 0)}개

**기준**:
- API route: 150줄 이하
- Server lib: 250줄 이하
- Client lib: 200줄 이하
- React component: 350줄 이하
- Python module: 350줄 이하

"""

    # 초과 파일 목록
    if mod_results.get('exceeding_files'):
        md_report += "**기준 초과 파일**:\n"
        for file_info in mod_results.get('exceeding_files', []):
            md_report += f"- {file_info['category']}: {file_info['file']} ({file_info['lines']} / {file_info['max']} 줄, +{file_info['excess']})\n"
    else:
        md_report += "**기준 초과 파일**: 없음 ✓\n"

    md_report += f"""
---

## 보안 정적 감사

### 상태: {sec_results.get('status', 'ERROR')}

**집계**:
- 스캔 파일: {sec_results.get('scanned_files', 0)}개
- 발견 이슈: {sec_results.get('issues_found', 0)}개

**검사 항목**:
- shell: true / shell=True ✓
- exec() / execSync ✓
- fs.rm / fs.unlink / fs.rmdir ✓
- os.remove / shutil.rmtree ✓
- local_file_map.json write ✓
- token/payload console.log ✓
- auto rollback ✓

"""

    if sec_results.get('issues'):
        md_report += "**발견된 이슈**:\n"
        for issue in sec_results.get('issues', [])[:10]:
            md_report += f"- {issue['severity']}: {issue['description']} in {issue['file']}:{issue['line']}\n"
    else:
        md_report += "**발견된 이슈**: 없음 ✓\n"

    md_report += f"""
---

## Component Line Count 감사

### 상태: {comp_results.get('status', 'ERROR')}

**집계**:
- 총 component: {comp_results.get('summary', {}).get('total_components', 0)}개
- 총 라인: {comp_results.get('summary', {}).get('total_lines', 0)}줄
- 평균: {comp_results.get('summary', {}).get('avg_lines', 0)}줄/파일
- 350줄 초과: {comp_results.get('summary', {}).get('exceeds_350', 0)}개
- 400줄 초과: {comp_results.get('summary', {}).get('exceeds_400', 0)}개

**상위 10개 큰 Component**:
"""

    for comp in comp_results.get('top_10_largest', []):
        exceeds = ' ⚠️' if comp['exceeds_350'] else ''
        md_report += f"- {comp['file']}: {comp['lines']}줄{exceeds}\n"

    md_report += f"""
---

## 다음 단계

1. FAIL 항목 수정 필요
2. WARN 항목 검토 및 개선
3. 자동 점검 스크립트 정기 실행 (CI/CD 통합)
4. fixture 기반 smoke test 추가
5. 실제 사용자 파일 이동 테스트 (별도 sandbox 환경)

---

**최종 판정**: {overall_status}
**검증 시점**: {datetime.now().isoformat()}
"""

    return json_report, md_report

if __name__ == '__main__':
    json_report, md_report = generate_report()

    # 파일 저장
    reports_dir = Path('docs/reports')
    reports_dir.mkdir(parents=True, exist_ok=True)

    json_path = reports_dir / 'local_file_map_auto_control_1.json'
    md_path = reports_dir / 'local_file_map_auto_control_1.md'

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_report, f, indent=2, ensure_ascii=False)

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_report)

    print(f"✓ 보고서 생성 완료", file=sys.stderr)
    print(f"  JSON: {json_path}", file=sys.stderr)
    print(f"  Markdown: {md_path}", file=sys.stderr)
    print(f"  상태: {json_report['overall_status']}", file=sys.stderr)

    sys.exit(0)
