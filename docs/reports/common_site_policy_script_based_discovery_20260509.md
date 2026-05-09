# COMMON_SITE_POLICY_SCRIPT_BASED_DISCOVERY_1 보고서 (2026-05-09)

## 1. 작업 목적

G2B 전용이 아니라 모든 업무 사이트에 공통 적용 가능한
**스크립트 기반 site policy / discovery / preflight / readonly smoke / report** 구조 구축.

수동 확인이나 임시 실행 없이, 모든 점검·등록·검증·리포트 생성을 스크립트로 수행한다.
이번 작업에서는 실제 사이트 접속 없이 dry-run runner만 만든다.

---

## 2. 신규 파일 목록

### configs/site_policies/ (예시 JSON 3개)

| 파일 | site_id | risk_level |
|---|---|---|
| g2b.json | g2b (조달청) | HIGH |
| hometax.json | hometax (홈택스) | MEDIUM |
| mss.json | mss (중소벤처기업부) | MEDIUM |

공통 정책: `execution_location=LOCAL_AGENT_REQUIRED`, `credential_policy=NO_CREDENTIAL_CAPTURE`, `capture_policy=NO_SCREENSHOT_NO_HAR`

### scripts/ (신규 7개)

| 스크립트 | 역할 |
|---|---|
| validate_site_policy_config.py | JSON config 필드·값 검증 + 위험 경로 경고 |
| build_discovery_candidates_from_fixture.py | fixture → DiscoveryCandidate 목록 생성 |
| validate_discovery_candidates.py | candidate JSON 안전성 검증 |
| run_allowlist_preflight.py | preflight_expansion 일괄 실행 + ALLOW/REVIEW/BLOCKED 분류 |
| build_readonly_smoke_plan.py | ALLOW_REGISTER 후보 → smoke plan JSON 생성 |
| run_readonly_smoke_dryrun.py | smoke plan dry-run 실행 (실제 브라우저 없음) |
| generate_policy_smoke_report.py | preflight + dry-run 결과 → Markdown 리포트 |

---

## 3. 파이프라인 흐름

```
[1] validate_site_policy_config.py
    ↓ (JSON config 검증)
[2] build_discovery_candidates_from_fixture.py
    ↓ (candidates JSON)
[3] validate_discovery_candidates.py
    ↓ (안전성 확인)
[4] run_allowlist_preflight.py
    ↓ (preflight JSON: ALLOW/REVIEW/BLOCKED)
[5] build_readonly_smoke_plan.py
    ↓ (smoke plan JSON: DRY_RUN 단계만)
[6] run_readonly_smoke_dryrun.py
    ↓ (smoke result JSON)
[7] generate_policy_smoke_report.py
    → Markdown 리포트
```

---

## 4. G2B 파이프라인 실행 결과

### 4-1. Config 검증

```
✅ PASS  configs/site_policies/g2b.json  site_id=g2b
✅ PASS  configs/site_policies/hometax.json  site_id=hometax
✅ PASS  configs/site_policies/mss.json  site_id=mss
```

### 4-2. Discovery Candidates (g2b fixture 11건)

| # | 타입 | 라벨 | 결과 |
|---|---|---|---|
| 1 | menu_candidate | 입찰공고 | ✅ |
| 2 | menu_candidate | 공사공고 | ✅ |
| 3 | page_title_candidate | 나라장터 입찰공고 목록 | ✅ |
| 4 | table_header_candidate | 공고번호 | ✅ |
| 5 | table_header_candidate | 공고명 | ✅ |
| 6 | table_header_candidate | 공고기관 | ✅ |
| 7 | download_link_candidate | 공고문 다운로드 | ✅ |
| 8 | download_link_candidate | 첨부파일 다운로드 | ✅ |
| 9 | field_candidate | 검색어 | ✅ |
| 10 | button_candidate | 검색 | ✅ |
| 11 | submit_button_candidate | 투찰 제출 | ✅ |

### 4-3. Preflight 결과

| 총 | ALLOW | REVIEW | BLOCKED | 자동승인 |
|---|---|---|---|---|
| 11 | 8 | 3 | 0 | 8 |

- ALLOW_REGISTER: menu, page_title, table_header, download_link (LOW risk 자동 등록 가능)
- REVIEW_REQUIRED: field, button, submit_button (사용자 검토 필요)

### 4-4. Smoke Plan (8단계, ALLOW 후보만)

| 단계 | 액션 | 라벨 |
|---|---|---|
| 1 | navigate_and_check_label | 입찰공고 |
| 2 | navigate_and_check_label | 공사공고 |
| 3 | verify_page_title | 나라장터 입찰공고 목록 |
| 4 | verify_table_column | 공고번호 |
| 5 | verify_table_column | 공고명 |
| 6 | verify_table_column | 공고기관 |
| 7 | verify_link_visible | 공고문 다운로드 |
| 8 | verify_link_visible | 첨부파일 다운로드 |

### 4-5. Dry-run 결과

**8/8 통과** (DRY_RUN_PASS) — 실제 브라우저 접속 없음

---

## 5. 금지 동작 확인

신규 스크립트 7개 내 playwright/chromium/headless 호출: **0건**

- 실제 사이트 접속 없음
- 로그인 없음
- 스크린샷 없음
- HAR 캡처 없음
- credential 입력 없음

---

## 6. 테스트 결과

| 파일 | 테스트 | 결과 |
|---|---|---|
| test_validate_site_policy_config_20260509.py | 9 | ✅ |
| test_build_discovery_candidates_script_20260509.py | 7 | ✅ |
| test_run_allowlist_preflight_script_20260509.py | 3 | ✅ |
| test_build_smoke_plan_script_20260509.py | 5 | ✅ |
| test_run_smoke_dryrun_script_20260509.py | 9 | ✅ |
| **신규 합계** | **33** | **33/33 ✅** |

전체 회귀: **5183 passed, 7 skipped** (이전 5150 → +33).

---

## 7. 남은 작업

- 실제 사이트 live runner 연결 (현재는 dry-run만)
- 3개 사이트(hometax, mss) fixture 고도화
- REVIEW_REQUIRED 후보의 사용자 승인 → ALLOW 전환 플로우
- smoke plan → action registry 자동 등록 연결

---

**작업명**: COMMON_SITE_POLICY_SCRIPT_BASED_DISCOVERY_1
**작성일**: 2026-05-09
**상태**: ✅ 완료
