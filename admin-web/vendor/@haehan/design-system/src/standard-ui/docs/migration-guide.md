# 표준 UI 마이그레이션 가이드

## 기존 FastAPI HTML 인라인 → 표준 UI 전환

1. FastAPI `HTMLResponse` 인라인 HTML 제거
2. `AppShell` + 해당 페이지 컴포넌트로 교체
3. API 호출 코드는 페이지 레벨에서만, 컴포넌트에는 데이터만 props로 전달

## 모델하우스(23. 입찰 조회 및 분석) 기준 차이

| 항목 | 모델하우스 | 표준 UI |
|------|-----------|---------|
| 프레임워크 | Next.js (입찰 서비스 전용) | 독립 패키지 (React) |
| 라우팅 | Next.js App Router | 사용 앱이 결정 |
| 인증 | g2b_token localStorage | 없음 (상위 앱 담당) |
| API | G2B_API_BASE 직접 호출 | 없음 (props만) |
| 업무 데이터 | 소방공사 입찰 도메인 | 없음 (범용) |

## 단계

1. `import from '@/standard-ui'`로 컴포넌트 참조
2. 페이지에서 데이터 로딩 후 props로 전달
3. 레이아웃: AppShell 적용
4. 기존 FastAPI HTML 점진적 교체
