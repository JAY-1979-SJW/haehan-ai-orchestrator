import json
from pathlib import Path
from collections import Counter

print("=" * 70)
print("Phase 3.5: 감사 로그 검증")
print("=" * 70)

# L2 감사 로그
print("\n[1] L2 감사 로그 (감사/추적)")
audit_file = Path("data/audit/L2_audit/browser_audit_20260510.jsonl")
if audit_file.exists():
    events = []
    with open(audit_file) as f:
        for line in f:
            events.append(json.loads(line))
    
    print(f"  ✓ 총 {len(events)} 이벤트")
    
    # 이벤트 타입별 집계
    event_types = Counter(e['event'] for e in events)
    print(f"\n  이벤트 유형별 집계:")
    for event_type, count in sorted(event_types.items()):
        print(f"    - {event_type}: {count}")
    
    # 마지막 5개 이벤트
    print(f"\n  마지막 5개 이벤트:")
    for i, e in enumerate(events[-5:], 1):
        print(f"    {i}. {e['event']} @ {e['ts']}")
else:
    print(f"  ✗ 파일 없음: {audit_file}")

# L3 세션 로그
print("\n[2] L3 세션 로그 (로그인 감지)")
session_file = Path("data/audit/L3_session/session_events_202605.jsonl")
if session_file.exists():
    sessions = []
    with open(session_file) as f:
        for line in f:
            sessions.append(json.loads(line))
    
    print(f"  ✓ 총 {len(sessions)} 이벤트")
    
    # 이벤트 타입별 집계
    event_types = Counter(e['event'] for e in sessions)
    print(f"\n  이벤트 유형별 집계:")
    for event_type, count in sorted(event_types.items()):
        print(f"    - {event_type}: {count}")
    
    # 로그인 감지 이벤트 찾기
    login_events = [e for e in sessions if 'LOGIN' in e['event']]
    if login_events:
        print(f"\n  로그인 감지 이벤트:")
        for e in login_events:
            print(f"    - {e['event']}: {e.get('domain')} @ {e['ts']}")
else:
    print(f"  ✗ 파일 없음: {session_file}")

# L1 운영 로그
print("\n[3] L1 운영 로그 (운영 정보)")
runtime_file = Path("data/audit/L1_runtime/browser_runtime_20260510.jsonl")
if runtime_file.exists():
    runtime = []
    with open(runtime_file) as f:
        for line in f:
            runtime.append(json.loads(line))
    
    print(f"  ✓ 총 {len(runtime)} 이벤트")
    
    # 이벤트 타입별 집계
    event_types = Counter(e['event'] for e in runtime)
    print(f"\n  이벤트 유형별 집계:")
    for event_type, count in sorted(event_types.items()):
        print(f"    - {event_type}: {count}")
else:
    print(f"  ✗ 파일 없음: {runtime_file}")

print("\n" + "=" * 70)
print("✓ Phase 3.5 완료")
print("=" * 70)
