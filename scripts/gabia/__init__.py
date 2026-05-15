"""Gabia site module.

가비아(gabia.com) 도메인/DNS/호스팅/메일/결제/계정 관련 자동화 경계 모듈.

업무 범위:
  - 도메인 상태/만료일/DNS 레코드 조회 (read-only)
  - DNS 레코드 변경, 도메인 연장/이전: APPROVAL_REQUIRED
  - 로그인/OTP/2FA/결제: USER_DIRECT_REQUIRED
  - 비밀번호/세션/쿠키 추출: BLOCKED

주의: 실제 브라우저 자동화는 로컬 에이전트에 위임하거나 사용자 직접 수행 필요.
"""
