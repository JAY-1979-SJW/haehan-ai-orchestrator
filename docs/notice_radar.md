# 정부공고 첨부파일 자동분석 기능

`notice_radar`는 정부·공공기관 공고를 대표님 사업 관점에서 자동 검토하기 위한 패키지입니다.

## 처리 흐름

1. 공고 상세 URL 접속
2. Playwright 렌더링 우선, 실패 시 HTTP 조회
3. PDF/HWP/HWPX/XLSX/ZIP 첨부 링크 탐색
4. 첨부파일 다운로드
5. PDF, HWPX, XLSX, ZIP 텍스트 추출
6. 신청자격, 제출서류, 마감, 기술노출 위험, 대표님 사업 적합도 분석
7. `analysis.json`과 `summary.md` 생성

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
from notice_radar import analyze_notice_url

analysis = analyze_notice_url(
    "https://www.k-startup.go.kr/...",
    source="K-Startup",
    title="정부 첫 실증·구매 프로젝트 스마트도시 창업기업 모집",
)

print(analysis.to_markdown())
```

이미 다운로드한 첨부 폴더만 분석할 수도 있습니다.

```python
from notice_radar import analyze_notice_folder

analysis = analyze_notice_folder(
    "storage/notices/smart_city_project",
    title="정부 첫 실증·구매 프로젝트 스마트도시 창업기업 모집",
    source="K-Startup",
)
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
pytest tests/test_notice_radar.py
```

## 현재 한계

- HWP 바이너리는 직접 파싱하지 않고 HWPX 변환 후 분석하는 구조입니다.
- 이미지 스캔 PDF는 OCR이 아니므로 텍스트 추출이 제한될 수 있습니다.
- 사이트별 로그인·보안 다운로드는 별도 승인형 브라우저 작업으로 연결해야 합니다.
