# G2B 공개 공고 Read-Only Live Execution 보고서

- 실행일시: 2026-05-07T15:16:35.666973+00:00
- fixture: C:\Users\skyjw\OneDrive\03. PYTHON\35. haehan-ai-orchestrator\tests\fixtures\g2b_public_notice_workflow_fixture_20260507.json

## 요약

| 항목 | 수 |
|------|-----|
| 총 케이스 | 18 |
| 허용 케이스 | 5 |
| live 실행 완료 | 5 |
| 차단 케이스 | 10 |
| gate BLOCK 확인 | 10 |
| 검증 필요 케이스 | 2 |

## 정책 준수

- local_agent_required: True
- server_browser_used: False
- download_auto_allowed: False
- click/type/fill/submit 실행 없음
- cookie/session/token/password/otp 저장 없음

## 케이스별 결과

- **wf_01** `g2b_apex_read_allowed` op=read expected=ALLOWED → **LIVE_PASS** | title: 시스템 접근 안내 | final_url: https://g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do
- **wf_02** `g2b_www_open_url_apex_normalized` op=open_url expected=ALLOWED → **LIVE_PASS** | title: 시스템 접근 안내 | final_url: https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001l.do
- **wf_03** `g2b_www_navigate_allowed` op=navigate expected=ALLOWED → **LIVE_PASS** | title: 시스템 접근 안내 | final_url: https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001m.do
- **wf_04** `g2b_detail_read_allowed` op=read expected=ALLOWED → **LIVE_PASS** | title: 시스템 접근 안내 | final_url: https://g2b.go.kr/pt/menu/ntn01/pta02/ptb04001l.do
- **wf_05** `g2b_login_path_blocked` op=navigate expected=BLOCKED → **GATE_BLOCK_CONFIRMED**
- **wf_06** `g2b_cert_path_blocked` op=navigate expected=BLOCKED → **GATE_BLOCK_CONFIRMED**
- **wf_07** `g2b_bid_path_blocked` op=navigate expected=BLOCKED → **GATE_BLOCK_CONFIRMED**
- **wf_08** `g2b_contract_path_blocked` op=navigate expected=BLOCKED → **GATE_BLOCK_CONFIRMED**
- **wf_09** `g2b_payment_path_blocked` op=navigate expected=BLOCKED → **GATE_BLOCK_CONFIRMED**
- **wf_10** `g2b_submit_operation_blocked` op=submit expected=BLOCKED → **GATE_BLOCK_CONFIRMED**
- **wf_11** `g2b_click_operation_blocked` op=click expected=BLOCKED → **GATE_BLOCK_CONFIRMED**
- **wf_12** `g2b_type_operation_blocked` op=type expected=BLOCKED → **GATE_BLOCK_CONFIRMED**
- **wf_13** `g2b_fill_operation_blocked` op=fill expected=BLOCKED → **GATE_BLOCK_CONFIRMED**
- **wf_14** `g2b_download_operation_blocked` op=download expected=BLOCKED → **GATE_BLOCK_CONFIRMED**
- **wf_15** `g2b_shop_needs_verification` op=read expected=NEEDS_VERIFICATION → **NEEDS_VERIFICATION_CONFIRMED**
- **wf_16** `g2b_unknown_subdomain_needs_verification` op=read expected=NEEDS_VERIFICATION → **NEEDS_VERIFICATION_CONFIRMED**
- **wf_17** `g2b_file_list_read_allowed_no_download` op=read expected=ALLOWED → **LIVE_PASS** | title: 시스템 접근 안내 | final_url: https://www.g2b.go.kr/pt/menu/ntn01/pta02/ptb02001m.do
- **wf_18** `g2b_apex_safe_to_execute_false` op=read expected= → **SKIPPED**

---
보고서 자동 생성. 민감정보 포함 금지.