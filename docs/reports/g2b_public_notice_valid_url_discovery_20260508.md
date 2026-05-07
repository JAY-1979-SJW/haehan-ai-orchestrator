# G2B 공개 공고 유효 URL Discovery 보고서

- 실행일시: 2026-05-07T15:49:05.279047+00:00
- actual_live_required: True
- mock_used: False
- local_agent_used: True
- server_browser_used: False

## 기존 fixture 콘텐츠 판정 요약

- 총 허용 fixture: 5
- CONTENT_VALID_PASS: 0
- REACHABLE_BUT_NOT_CONTENT_VALID: 4
- CONTENT_INVALID: 0
- CONTENT_UNKNOWN: 0

## 후보 URL 수집 결과

- 전체 후보: 2
- safe 후보: 2
- blocked 후보: 0
- needs_verification 후보: 0

## Discovery CONTENT_VALID_PASS 후보

- 없음 (WARN: 발견된 CONTENT_VALID_PASS 후보 없음)

## 정책 준수

- click/type/fill/submit/download 실행: 없음
- cookie/session/token/password/otp 저장: 없음
- max-depth: 1
- 서버 브라우저 G2B 접속: 없음
- wildcard 도메인 허용: 없음
- 기존 fixture 직접 수정: 없음
- DB write: 없음

## 케이스별 상세

### wf_01 — https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do
- live_verdict: LIVE_PASS
- content_verdict: REACHABLE_BUT_NOT_CONTENT_VALID
- invalid_reason: 시스템 접근 안내; 요청하신 페이지를 찾을수 없습니다; 올바르지 않은 URL
- positive_signals: []
- negative_signals: ['시스템 접근 안내', '요청하신 페이지를 찾을수 없습니다', '올바르지 않은 URL']
- safe_candidates: 1

### wf_02 — https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do
- live_verdict: LIVE_PASS
- content_verdict: REACHABLE_BUT_NOT_CONTENT_VALID
- invalid_reason: 시스템 접근 안내; 요청하신 페이지를 찾을수 없습니다; 올바르지 않은 URL
- positive_signals: []
- negative_signals: ['시스템 접근 안내', '요청하신 페이지를 찾을수 없습니다', '올바르지 않은 URL']
- safe_candidates: 1

### wf_03 — https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001m.do
- live_verdict: LIVE_PASS
- content_verdict: REACHABLE_BUT_NOT_CONTENT_VALID
- invalid_reason: 시스템 접근 안내; 요청하신 페이지를 찾을수 없습니다; 올바르지 않은 URL
- positive_signals: []
- negative_signals: ['시스템 접근 안내', '요청하신 페이지를 찾을수 없습니다', '올바르지 않은 URL']
- safe_candidates: 1

### wf_04 — https://g2b.go.kr/pt/menu/ntn01/pta02/ptb04001l.do
- live_verdict: LIVE_PASS
- content_verdict: REACHABLE_BUT_NOT_CONTENT_VALID
- invalid_reason: 시스템 접근 안내; 요청하신 페이지를 찾을수 없습니다; 올바르지 않은 URL
- positive_signals: []
- negative_signals: ['시스템 접근 안내', '요청하신 페이지를 찾을수 없습니다', '올바르지 않은 URL']
- safe_candidates: 1
