# 정부공고 첨부파일 자동분석 기능

`notice_radar`는 정부·공공기관 공고를 대표님 사업 관점에서 자동 검토하기 위한 패키지입니다.

## 처리 흐름

1. 대표님이 브라우저에서 공고 상세페이지를 직접 엽니다.
2. 앱이 현재 브라우저 탭에 CDP로 연결합니다.
3. 현재 탭의 본문, 제목, URL, 첨부 링크를 수집합니다.
4. 현재 브라우저 쿠키/세션으로 첨부파일을 다운로드합니다.
5. PDF, HWPX, XLSX, ZIP 텍스트를 추출합니다.
6. 신청자격, 제출서류, 마감, 기술노출 위험, 대표님 사업 적합도 분석을 수행합니다.
7. `analysis.json`과 `summary.md`를 생성합니다.

## 브라우저 실행 조건

현재 열린 탭을 읽으려면 Chrome 또는 Edge가 원격 디버깅 포트로 실행되어야 합니다.

Windows 예시:

```bash
chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\haehan-browser-profile"
```

환경변수로 포트를 바꿀 수 있습니다.

```bash
set NOTICE_RADAR_CDP_URL=http://127.0.0.1:9222
```

## 현재 프로젝트 실행 API

대시보드 Flask 앱에 `notice_router.py`가 등록되어 있으므로, 대시보드 실행 상태에서 바로 호출할 수 있습니다.

```bash
python dashboard.py
```

상태 확인:

```bash
curl -u "$ORCH_DASHBOARD_USER:$ORCH_DASHBOARD_PASSWORD" \
  http://127.0.0.1:5050/api/v1/notices/health
```

현재 브라우저 탭 분석:

```bash
curl -u "$ORCH_DASHBOARD_USER:$ORCH_DASHBOARD_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{"source":"K-Startup","title":"정부 첫 실증·구매 프로젝트 스마트도시 창업기업 모집"}' \
  http://127.0.0.1:5050/api/v1/notices/analyze-current-browser
```

여러 탭이 열려 있을 때 특정 사이트 탭을 지정하려면:

```bash
curl -u "$ORCH_DASHBOARD_USER:$ORCH_DASHBOARD_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{"target_url_contains":"k-startup.go.kr","source":"K-Startup"}' \
  http://127.0.0.1:5050/api/v1/notices/analyze-current-browser
```

공고 URL 직접 분석도 유지합니다.

```bash
curl -u "$ORCH_DASHBOARD_USER:$ORCH_DASHBOARD_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.k-startup.go.kr/...","source":"K-Startup","title":"정부 첫 실증·구매 프로젝트 스마트도시 창업기업 모집"}' \
  http://127.0.0.1:5050/api/v1/notices/analyze-url
```

이미 다운로드한 첨부 폴더 분석:

```bash
curl -u "$ORCH_DASHBOARD_USER:$ORCH_DASHBOARD_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{"folder":"storage/notices/smart_city_project","title":"정부 첫 실증·구매 프로젝트 스마트도시 창업기업 모집","source":"K-Startup"}' \
  http://127.0.0.1:5050/api/v1/notices/analyze-folder
```

보안상 로컬 폴더 분석은 아래 경로 안으로 제한합니다.

- `storage/notices`
- `storage/uploads`
- `storage/inbox_attachments`

## 대표님 맞춤 판단 항목

- 개인사업자 가능 여부
- 법인 필수 여부
- 창업연수 제한
- 기술자료·소스코드·알고리즘 공개 위험
- 자부담 또는 민간부담금 여부
- 실증기관·수요처·구매기관 필요 여부
- CAD 자동물량 산출, 소방설비, 건설, 스마트도시, AI 소프트웨어 적합성

## Python 사용 예시

```python
from notice_radar import analyze_current_browser_notice

analysis = analyze_current_browser_notice(
    cdp_url="http://127.0.0.1:9222",
    source="K-Startup",
    title="정부 첫 실증·구매 프로젝트 스마트도시 창업기업 모집",
)

print(analysis.to_markdown())
```

## 출력 파일

```text
storage/notices/<공고명>/
  notice_page.txt
  candidate.json
  attachments/
  analysis.json
  summary.md
```

## 테스트

```bash
pytest tests/test_notice_radar.py tests/test_notice_router.py
```

## 현재 한계

- HWP 바이너리는 직접 파싱하지 않고 HWPX 변환 후 분석하는 구조입니다.
- 이미지 스캔 PDF는 OCR이 아니므로 텍스트 추출이 제한될 수 있습니다.
- href 없이 자바스크립트 클릭만으로 내려받는 첨부는 사이트별 클릭 수집기를 추가해야 할 수 있습니다.
