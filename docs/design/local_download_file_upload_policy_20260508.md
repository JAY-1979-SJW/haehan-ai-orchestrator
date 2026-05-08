# LOCAL_DOWNLOAD_FILE_UPLOAD_POLICY 설계 문서

작성일: 2026-05-08  
작업명: LOCAL_DOWNLOAD_FILE_UPLOAD_POLICY_1

---

## 개요

로컬 Playwright 에이전트가 외부 사이트에서 다운로드한 파일을 서버에 업로드할 때
어떤 파일이 허용되고 어떤 파일이 차단되는지 정책을 정의한다.

---

## 신규 모듈

| 파일 | 역할 |
|---|---|
| `local_agent/download_policy.py` | 파일별 업로드 허용/차단 판정 |
| `local_agent/download_result_sanitizer.py` | 다운로드 결과에서 민감 필드 제거 |
| `local_agent/download_upload_manifest.py` | 서버 전송용 safe manifest 생성 |
| `server/local_agent_file_upload_policy.py` | 서버 사이드 manifest 검증 및 수신 정책 |

---

## 허용 확장자

```
.pdf .hwpx .xlsx .xls .docx .zip .txt .csv .png .jpg .jpeg
```

## 차단 확장자

인증서/키:
```
.pfx .p12 .der .key .pem .crt .cer .jks .p7b .p7c .p8 .p15 .pub
```

실행파일:
```
.exe .msi .bat .cmd .ps1 .js .vbs .sh .py .jar .dll .so .dmg .pkg
```

기타 위험:
```
.lnk .scr .com .hta .reg
```

---

## 차단 조건 (우선순위 순)

1. task 외부 파일 (해당 task가 다운로드하지 않은 파일)
2. NPKI/인증서 경로 (`NPKI`, `usercert`, `signCert`, `npkicard` 등 경로 포함)
3. 차단 확장자
4. 민감 파일명 패턴 (`password`, `secret`, `token`, `cookie`, `session`, `otp` 등)
5. 허용 확장자 외 파일
6. 50MB 초과 파일

---

## safe manifest 구조

```json
{
  "task_id": "string",
  "files": [
    {
      "file_id": "uuid",
      "safe_name": "notice_attachment.pdf",
      "extension": ".pdf",
      "size_bytes": 12345,
      "mime_type": "application/pdf",
      "upload_allowed": true,
      "blocked_reason": null,
      "certificate_file_detected": false
    }
  ],
  "sensitive_data_detected": false,
  "certificate_file_detected": false,
  "total_files": 1,
  "allowed_count": 1,
  "blocked_count": 0
}
```

manifest에서 제거되는 필드:
- `file_path`, `local_path`, `absolute_path`
- `cookie`, `session`, `token`, `password`, `otp`, `certificate_password`
- `file_content`, `file_binary`, `file_data`

---

## 서버 정책

- 서버는 외부 사이트에서 직접 파일을 다운로드하지 않는다.
- 서버는 파일 바이너리를 수신하지 않는다. (manifest 메타만 수신)
- 서버는 인증서/NPKI 파일을 수신하지 않는다.
- manifest에 `certificate_file_detected=true`가 포함되면 전체 거부.
- 서버 허용 MIME: pdf, hwpx, xlsx, xls, docx, zip, txt, csv, png, jpg
- 서버 파일 크기 제한: 50MB

---

## 원본 파일 처리

- 원본 파일은 삭제하지 않는다.
- 원본 경로는 서버에 전송하지 않는다.
- 사용자 PC 다운로드 폴더 전체 스캔 금지.
- 해당 task가 다운로드한 파일만 manifest에 포함한다.
