"""ai_orchestrator.cad — cad-quantity(cad-backend) 프록시 서브패키지.

이 패키지는 독립 배포된 cad-backend FastAPI(:8000) 를 오케스트레이터의
/api/v1/cad/* 경로 뒤로 감춘다. 클라이언트는 오케스트레이터만 보고,
인증/승인/감사 게이트를 통과한 호출만 상류로 중계된다.
"""
