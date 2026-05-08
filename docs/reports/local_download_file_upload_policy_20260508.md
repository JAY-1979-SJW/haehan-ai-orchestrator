# LOCAL_DOWNLOAD_FILE_UPLOAD_POLICY_1 실행 보고서

작성일: 2026-05-08

---

## 기준선

- 시작 HEAD: 566a975
- pytest 기준: 3691 passed, 6 skipped, 0 failed

---

## 구현 내용

### download_policy.py (신규)
- 허용 확장자: pdf/hwpx/xlsx/xls/docx/zip/txt/csv/png/jpg/jpeg
- 차단 확장자: pfx/p12/der/key/pem/crt/cer + exe/msi/bat/cmd/ps1/js/vbs 등
- NPKI 경로 차단 (확장자 검사보다 우선)
- 민감 파일명 패턴 차단 (password/secret/token/cookie/session/otp)
- task 외부 파일 차단
- 50MB 초과 파일 차단
- 원본 파일 삭제 없음, 폴더 전체 스캔 없음

### download_result_sanitizer.py (신규)
- file_path/local_path/absolute_path 제거
- cookie/session/token/password/otp/cert_password 제거
- file_content/file_binary 제거
- 안전 필드 9개 False 강제
- 파일 항목별 허용 필드(file_id/safe_name/extension/size_bytes/mime_type/upload_allowed/blocked_reason)만 유지

### download_upload_manifest.py (신규)
- build_manifest(): download_policy + sanitizer 통합
- validate_manifest(): 원본 경로 노출 포함 검증
- is_safe_manifest(): 서버 전송 안전성 확인

### server/local_agent_file_upload_policy.py (신규)
- validate_upload_manifest(): manifest 수신 검증
- certificate_file_detected=true 시 전체 거부
- 서버 허용 MIME 목록 관리
- 서버는 파일 바이너리 수신 안 함

---

## 테스트 결과

| 테스트 파일 | 결과 |
|---|---|
| test_local_download_file_upload_policy_20260508.py | 41 passed |
| test_local_download_result_sanitizer_20260508.py | 16 passed |
| test_local_download_upload_manifest_20260508.py | 29 passed |
| 전체 pytest | 3777 passed, 6 skipped, 0 failed |

---

## 보안 정책 준수

| 항목 | 상태 |
|---|---|
| 인증서 파일 업로드 | 금지 (pfx/p12/der/key/pem/crt/cer 차단) |
| NPKI 경로 파일 | 금지 |
| cookie/session/password/OTP/cert password | manifest에 미포함, 필드 제거 |
| 원본 로컬 경로 노출 | 제거 |
| 서버 외부 브라우저 실행 | 없음 |
| 자동 submit/sign/payment/bid | 없음 |
| 파일 바이너리 서버 전송 | 없음 (메타만 전송) |

---

## 남은 과제

- 나라장터 read-only E2E 실제 테스트
- OS 트레이 상주/자동시작 정책은 별도 승인 후 진행
