# 해한 디자인 시스템

> **공용 본관 프로젝트** — 모든 해한 앱의 UI 기준

## 이 프로젝트는

비서앱, 입찰앱, CAD앱, 출퇴근앱, 위험성평가표, 문서 자동화 앱에서
공통으로 사용할 UI 기준을 관리하는 디자인 시스템이다.

단순 웹사이트가 아니라 공통 **색상, 여백, 폰트, 카드, 테이블, 버튼,
상태표시, 페이지 패턴**을 관리하는 디자인 시스템이다.

## 기존 임시 표준 UI

기존 `haehan-ai-orchestrator` 내부의 `admin-web/src/standard-ui`는
임시 생성본이며, **이 프로젝트를 공용 본관으로 사용한다**.

각 앱은 이 디자인 시스템을 기준으로 UI를 맞춘다.

## 구조

```
haehan-design-system/
├─ app/                  Next.js App Router
│  ├─ layout.tsx
│  ├─ page.tsx           견본 화면 (디자인 시스템 쇼케이스)
│  └─ globals.css        CSS 변수 기반 디자인 토큰
├─ src/
│  └─ standard-ui/       공용 컴포넌트 패키지
│     ├─ tokens/         (colors, spacing, typography, radius, shadows)
│     ├─ components/     (layout, status, cards, tables, lists, forms, feedback)
│     ├─ patterns/       (페이지 패턴 문서)
│     ├─ docs/           (디자인 시스템 문서)
│     └─ index.ts
├─ package.json
├─ tsconfig.json
├─ next.config.mjs
├─ tailwind.config.ts
└─ postcss.config.mjs
```

## 브랜드 원칙

| 역할 | 색상 | 비율 |
|------|------|------|
| Accent | #F97316 (Orange) | 5% 이하 |
| Structure | #1E2D4A (Navy) | 10~20% |
| Neutral | #F5F7FA / #FFFFFF | 70~80% |

- 페이지 상단 **4px Orange Top Accent Line** 필수
- 사이드바 폭 **224px**, Navy 배경
- 기본 폰트 **Pretendard**, 14px

## 시작하기

```bash
npm install          # 의존성 설치 (이번 단계에서는 미실행)
npm run dev          # 개발 서버 실행 (port 3010)
npm run build        # 빌드
npm run typecheck    # 타입 검사
```

> ⚠️ 이번 단계에서는 `npm install`, `build`, 배포는 하지 않는다.

## 적용 대상 앱

- 비서앱 (haehan-ai-orchestrator / admin-web)
- 입찰앱 (23. 입찰 조회 및 분석)
- CAD 자동화
- 출퇴근 앱
- 위험성평가표 앱
- 문서 자동화 앱

## 공정표 위치

```
DS_ROOT_01 — 본관 디자인시스템 생성
DS_STORYBOOK_01 — Storybook 연결
DS_CONSUMER_REFERENCE_CONTRACT_01 — 소비 앱 참조 계약 고정
```

## 다른 앱에서 참조하는 방식

- 권장 패키지명: `@haehan/design-system`
- 현재는 로컬 file 참조 또는 workspace 참조 기준
- 각 앱은 컴포넌트를 복사하지 말고 이 패키지를 참조한다
- Next.js 앱은 필요 시 `next.config`에서 `transpilePackages`에 `@haehan/design-system` 추가
- 각 앱의 `app/layout.tsx` 또는 `globals.css`에서 디자인 토큰 CSS를 연결한다
- 앱별 색상/버튼/배지/테이블을 임의 생성하지 말고 공용 컴포넌트를 우선 사용한다

### 다른 앱 package.json 예시

```json
"dependencies": {
  "@haehan/design-system": "file:../00.디자인시스템"
}
```

### Next.js next.config 예시

```js
// next.config.mjs
const nextConfig = {
  transpilePackages: ["@haehan/design-system"],
};
export default nextConfig;
```

### 컴포넌트 import 예시

```typescript
import { Button, Input, Select } from '@haehan/design-system';
import { StatusBadge } from '@haehan/design-system';
import { MetricCard, GateStatusCard, WarehouseCard } from '@haehan/design-system';
import { TopAccentLine } from '@haehan/design-system';
import { ConstructionPhaseTable } from '@haehan/design-system';
import type { ConstructionPhaseRow } from '@haehan/design-system';
```

## 로컬 브라우저 접속 실패 시 기준

- `curl` 또는 `Invoke-WebRequest` HTTP 200이면 앱 서버 기동은 PASS
- 실제 브라우저 렌더링 실패는 별도 UI smoke 단계에서 점검
- DNS/서브도메인 공개 전에는 local browser smoke를 별도 PASS 시켜야 한다
- 현재 단계에서는 도메인 배포를 진행하지 않는다
- 향후 공개 도메인: `design.haehan-ai.kr` / Storybook: `storybook.design.haehan-ai.kr`
