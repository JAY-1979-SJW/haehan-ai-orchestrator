# User Field Test — Summary

- HEAD: `788054e`
- 일시: 2026-05-21 14:10 KST
- 테스터 PC: Windows 11, IP 220.79.246.190 (빌드 머신, allowlist 멤버)
- 외부 PC 사용: **아니오** (환경 제약 — `WARN_SAME_MACHINE_TEST_ONLY`)

## 산출물 sha256

- `dist/HaehanAI-Agent.zip` (87.5MB): `C69039EB562CF03AFE8C12FB47A542E03B60EFE8DD92E221B61128D248E419FB`
- `dist/HaehanAI-Agent/HaehanAI-Agent.exe`: `7CA125ABDCD0550CDE12954AFA95801972C27FDF9D5355A8CCFC483D99A32DE3`

## 13단계 결과

| # | 단계 | 결과 |
|---|------|------|
| 1 | zip → 깨끗한 폴더 (%TEMP%/haehan_field_test) extract | ✅ |
| 2 | exe --self-test (Python 없이) | ✅ ok=True, leaks=[] |
| 3 | exe --diagnostics (Python 없이) | ✅ rc=0, leak 0 |
| 4 | exe --gui (사이드바 4탭 + 트레이) | ✅ 6초 alive |
| 5 | --register (env code 사용) → 200 OK | ✅ agent_id la-9bc***22df |
| 6 | Windows Credential Manager 저장 | ✅ WinVaultKeyring |
| 7 | WSS auth_ok | ✅ |
| 8 | heartbeat (직전 공정에서 ack x2 검증) | ✅ |
| 9 | 재실행 자동 연결 → auth_ok 재수신 | ✅ |
| 10 | 오류 안내: TOKEN_NOT_STORED (잘못된 agent_id) | ✅ 한글 안내 |
| 11 | 오류 안내: --register 코드 미설정 (env 없음) | ✅ rc=2 + 안내 |
| 12 | SmartScreen / 백신 경고 | ❌ 본 환경 미발생 (외부 PC 검증 필요) |
| 13 | 사용자 피드백 | 수집 — 한글 인코딩 가이드 필요 (PowerShell / chcp 65001) |

## leak 검사

- 보고서 (`user_field_test_report.json`) 안에 `"device_token": "..."` raw 값 **0건**
- agent_id 표기는 모두 `la-9bc***22df` 마스킹
- Credential Manager 값 export 안 함

## desktop/ui (React) 미수정 확인

- 정책: 현재 라인은 `HaehanAI-Agent.exe` 만, `desktop/ui/*` / `desktop/ui_dist/*` 절대 손대지 않음
- 본 공정 staged/committed 파일에 `desktop/ui/*` **0건**

## 한계

- `WARN_SAME_MACHINE_TEST_ONLY` — 본 검증은 빌드 머신 = 테스터 머신. 외부 PC field test 미수행.
- `WARN_UNSIGNED_BINARY` — 코드 서명 OUT_OF_SCOPE (다음 공정 CODE_SIGNING_01).
- SmartScreen / 백신 경고는 **외부 다운로드 시점** 에서만 정확 확인됨 → 외부 PC field tester 필요.

## 외부 PC field tester 를 위한 runbook (`local_agent_external_field_runbook.md` 참고)

본 보고서를 토대로 외부 사용자 PC 에서 1) zip 다운로드 → 2) SmartScreen 응답 기록 → 3) 본 보고서 13 단계 재현 → 4) `user_field_test_report_external.json` 생성 → 5) git PR 또는 메일 회신.

## 최종 verdict

**WARN_SAME_MACHINE_TEST_ONLY** (spec 허용 — 모든 검증 가능 단계 PASS, 외부 PC 미수행 환경 제약)
