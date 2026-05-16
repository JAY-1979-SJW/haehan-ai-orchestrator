# 표준 UI Do / Don't

## ✅ Do

- TopAccentLine을 AppShell에 항상 포함한다
- StatusBadge에 statusColors 토큰을 사용한다
- 카드/버튼에 8px radius를 적용한다
- 컴포넌트에 업무 로직이 아닌 props만 전달한다
- 접근성 label/role을 명시한다

## ❌ Don't

- 컴포넌트 안에서 fetch/API 호출하지 않는다
- localStorage/cookie/session 접근하지 않는다
- 하드코딩된 업무 데이터를 컴포넌트에 포함하지 않는다
- 투찰/전자서명/결제 버튼을 자동 실행되도록 구현하지 않는다
- 토큰을 무시하고 임의 색상을 사용하지 않는다
- 모델하우스 원본 파일을 직접 수정하지 않는다
