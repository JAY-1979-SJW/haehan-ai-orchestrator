# Gate Page 패턴

## 용도
레이어 감사/보안/품질 게이트 결과 조회.

## 구성 요소
- PageContainer(variant=default)
- Alert (FAIL 있으면 최상단)
- GateStatusCard × 각 게이트 항목
- ConstructionPhaseTable (선택)

## 게이트 항목 예시
- FORBIDDEN_IMPORT
- SECURITY_PATTERN
- CIRCULAR_IMPORT
- FAT_SITE
- ROUTER_THINNESS
- STORAGE_BOUNDARY
- SERVER_BROWSER_GUARD

## 금지
- 게이트 결과 자동 무시/우회 버튼
- --no-verify 실행 버튼
