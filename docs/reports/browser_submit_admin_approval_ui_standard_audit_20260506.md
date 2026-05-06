# Browser Submit Admin Approval UI 표준 감사 보고서

**작성일:** 2026-05-06  
**타스크:** BROWSER_SUBMIT_ADMIN_APPROVAL_UI_STANDARDIZE_1  
**상태:** ✓ 표준 UI 분석 완료

## 1. 참조한 표준 UI 출처

### 참조 저장소
- **경로:** C:\Users\skyjw\OneDrive\03. PYTHON\31. construction-attendance
- **상태:** Read-only (수정 없음)
- **Git 작업:** 없음 (pull, commit, status 실행 금지)

### 참조 파일 목록 (6개)

| 파일 | 라인 | 용도 | 상태 |
|------|------|------|------|
| components/admin/ui/PageShell.tsx | 1-53 | 페이지 기본 구조/패딩 | ✓ 읽음 |
| components/admin/ui/PageHeader.tsx | 1-39 | 헤더 레이아웃/타이포그래피 | ✓ 읽음 |
| components/admin/ui/StatusBadge.tsx | 1-53 | 상태 배지 스타일 | ✓ 읽음 |
| components/admin/ui/Btn.tsx | 1-56 | 버튼 변형/크기 | ✓ 읽음 |
| components/admin/ui/DetailPanel.tsx | 1-83 | 슬라이드 패널 구조 | ✓ 읽음 |
| components/admin/ui/InfoRow.tsx | 1-61 | 정보 행 레이아웃 | ✓ 읽음 |

---

## 2. 표준 UI 패턴 분석 결과

### 2.1 페이지 구조 (PageShell)
```
bg-brand 배경
├─ sticky 헤더 (상단 고정, z-10)
│  └─ px-5 md:px-6, pt-5 md:pt-6, pb-3
└─ 본문 영역
   └─ px-5 md:px-6, pb-5 md:pb-6
```
**적용 대상:** SubmitApprovalPanel 래퍼

### 2.2 카드 컴포넌트 (SectionCard)
```
bg-card (흰색) 배경
rounded-[12px] (12px 라운드)
border border-brand (1px 네이비 보더)
p-5 (기본 패딩)
```
**적용 대상:** SubmitPreviewSummary, SubmitPreviewDetails, SubmitAuditRecordPanel

### 2.3 헤더/배지 (PageHeader + PageBadge)
**PageHeader:**
- h1: text-[20px] font-bold text-title-brand
- description: text-[12px] text-muted2-brand mt-1
- 레이아웃: flex flex-col sm:flex-row, justify-between

**PageBadge:**
- text-[11px] font-semibold
- px-2.5 py-1, rounded-full, border
- bg-footer text-muted-brand

**적용 대상:** SubmitApprovalPanel 제목 + 상태 배지

### 2.4 상태 배지 (StatusBadge)
**패턴:**
- text-[11px] font-semibold
- px-2 py-0.5, rounded-full, border
- 상태별 색상:
  - 대기: bg-yellow-light text-status-pending border-yellow
  - 승인: bg-green-light text-status-approved border-[#6EE7B7]
  - 취소: bg-red-light text-status-rejected border-[#F87171]

**적용 대상:** approval-status-badge, risk-level-badge, policy-verdict-badge

### 2.5 버튼 (Btn)
**변형:**
- primary: bg-brand (navy), hover:bg-brand-deeper
- orange: bg-brand-accent (orange), hover:bg-brand-accent-hover
- secondary: bg-white border border-brand, hover:bg-surface
- danger: bg-[#B91C1C]
- success: bg-[#059669]
- ghost: bg-transparent, border transparent

**크기:**
- sm: text-[12px], px-3 py-1.5, rounded-[7px]
- md: text-[13px], px-3.5 py-[7px], rounded-[8px]

**적용 대상:** approve-button, cancel-button

### 2.6 슬라이드 패널 (DetailPanel)
```
┌─ h-1 bg-brand-accent (4px 오렌지 상단 라인)
├─ 헤더 (px-5 py-4, border-bottom #E5E7EB)
│  ├─ h2: text-[15px] font-bold text-title-brand
│  ├─ subtitle: text-[12px] text-muted2-brand
│  └─ 닫기 버튼 (w-7 h-7, rounded-[6px])
├─ 본문 (flex-1 overflow-y-auto, px-5 py-5)
└─ 액션 (px-5 py-4, border-top #E5E7EB, gap-2)
```
**적용 대상:** SubmitPreviewDetails

### 2.7 정보 행 (InfoRow)
```
flex justify-between, py-[9px], border-b #F3F4F6
├─ 라벨: text-[12px] text-muted-brand, min-w-[72px]
└─ 값: text-[13px] font-medium text-title-brand
```
**적용 대상:** SubmitAuditRecordPanel의 각 정보 행

---

## 3. 현재 haehan-ai-orchestrator 구현 상태

### 3.1 SubmitApprovalPanel
**현재:** 기본 bg-white, border border-gray-200
**문제:** 
- 페이지 컨테이너 구조 없음
- 헤더 스타일 표준화 안 됨
- 상단 accent line이 absolute 배치로 부자연스러움

### 3.2 SubmitPreviewSummary
**현재:** space-y-4, p-3 bg-gray-50 field-summary
**문제:**
- border-gray-200 (표준: border-brand navy)
- rounded 값이 명확하지 않음 (표준: rounded-[12px])
- 배지 색상이 기본 Tailwind만 사용

### 3.3 SubmitPreviewDetails
**현재:** space-y-4, p-4 bg-gray-50, border border-gray-200
**문제:**
- 표준 배경은 bg-card (흰색)
- grid-cols-2/3 구성은 유지하되, 보더/스타일 개선 필요

### 3.4 SubmitAuditRecordPanel
**현재:** space-y-4, p-4 bg-slate-50, border border-slate-400
**문제:**
- InfoRow 스타일 미적용 (현재는 key:value 단순 나열)
- 배경색 표준화 필요 (bg-card)

---

## 4. 적용 계획

### 4.1 색상 기준 확립

**브랜드 색상 (Tailwind 커스텀):**
```
bg-brand: navy (#0F172A)
bg-card: white (#FFFFFF)
bg-footer: light gray (#F3F4F6)
bg-surface: lighter gray (#F9FAFB)
text-title-brand: navy (#0F172A)
text-body-brand: medium gray (#374151)
text-muted-brand: light gray (#6B7280)
text-muted2-brand: lighter gray (#9CA3AF)
bg-brand-accent: orange (#F97316)
bg-brand-accent-hover: darker orange (#EA580C)
```

### 4.2 컴포넌트별 개선 항목

**SubmitApprovalPanel:**
- [ ] PageShell 적용 (sticky header, padding)
- [ ] 상단 4px 오렌지 라인 개선
- [ ] 제목 스타일: text-[20px] font-bold text-title-brand
- [ ] 상태 배지: rounded-full, border, 상태색 적용

**SubmitPreviewSummary:**
- [ ] SectionCard 래퍼 적용 (rounded-[12px], border-brand)
- [ ] 제목들: text-[12px] font-medium text-muted-brand
- [ ] 값들: text-[13px] font-medium text-title-brand
- [ ] risk-level-badge: 상태별 색상 (high→red-light, etc.)

**SubmitPreviewDetails:**
- [ ] SectionCard 래퍼 적용
- [ ] InfoRow 스타일 적용
- [ ] h3 제목: text-[15px] font-bold text-title-brand
- [ ] 섹션 제목: text-[11px] font-bold text-muted-brand uppercase

**SubmitAuditRecordPanel:**
- [ ] SectionCard 래퍼 적용
- [ ] 각 정보 행: InfoRow 컴포넌트 재사용 또는 동일 스타일
- [ ] 헤더: flex gap-2 items-center, text-[12px] font-semibold
- [ ] 배지들: rounded-full, status color mapping

**Buttons:**
- [ ] approve-button: variant="orange" (bg-brand-accent)
- [ ] cancel-button: variant="secondary" (bg-white border-brand)
- [ ] 크기: md (text-[13px], px-3.5, rounded-[8px])

---

## 5. 타이포그래피 표준

| 용도 | 크기 | Weight | 색상 |
|------|------|--------|------|
| 페이지 제목 | 20px | bold | text-title-brand |
| 섹션 제목 | 15px | bold | text-title-brand |
| 라벨/필드 제목 | 12px | medium | text-muted-brand |
| 값/본문 | 13px | medium | text-title-brand |
| 배지 텍스트 | 11px | semibold | 상태별 |
| 설명/보조 | 12px | normal | text-muted2-brand |

---

## 6. 스페이싱 표준

| 용도 | 값 |
|------|-----|
| 카드 패딩 | p-5 (1.25rem) |
| 섹션 간 여백 | py-[9px] |
| 요소 간 갭 | gap-2, gap-3 |
| 페이지 여백 | px-5 md:px-6, pb-5 md:pb-6 |
| 보더 반경 | rounded-[12px] (카드), rounded-[8px] (버튼), rounded-full (배지) |

---

## 7. 보더 및 셰도우

**보더:**
- 카드: 1px border-brand
- 필드: 1px border-[#E5E7EB]
- 구분선: border-[#F3F4F6]

**섀도우:**
- 헤더/탭: 1px border-bottom
- 패널: shadow-xl (우측 슬라이드)

---

## 8. 반응형 설계

**Breakpoint:**
- Mobile: < sm (640px)
- Tablet/Desktop: >= sm (640px)

**적용:**
- px-5 md:px-6 (페이지 여백)
- text-[20px] sm:text-[24px] (제목)
- flex flex-col sm:flex-row (레이아웃)

---

## 9. 다음 단계

1. **STEP F:** UI 컴포넌트 실제 적용 시작
   - SubmitApprovalPanel 구조 개선
   - 각 자식 컴포넌트 스타일 동기화
   - Tailwind 클래스 정리

2. **STEP G:** 테스트 보강
   - 비주얼 렌더링 테스트
   - 상태 전환 테스트
   - 반응형 테스트

3. **STEP H:** 최종 closeout 보고서
   - 적용 결과 정리
   - 금지 항목 준수 확인
   - 변경 범위 확인

---

## 10. 주요 결론

✓ construction-attendance의 표준 UI는 매우 일관되고 체계화되어 있음  
✓ 6개 핵심 컴포넌트 패턴 파악 완료  
✓ 색상, 타이포, 스페이싱 기준 문서화 완료  
✓ haehan-ai-orchestrator의 Submit Approval UI 개선 범위 명확함  

---

**감사 일시:** 2026-05-06 13:00 KST  
**감사자:** Claude Code (Haiku 4.5)  
**상태:** ✓ 검증 완료, 적용 준비 완료
