"""민감 파일명 마스킹 및 인증 기반 표시 정책.

상용 리포트용 민감한 파일명을 마스킹하는 기능.
- 기본: 민감 파일명 마스킹
- 인증 후: 사용자가 본인 확인 완료 시 원본 파일명 표시 가능
- 조건: reveal_sensitive_names=True AND auth_verified=True 모두 만족해야 원본 표시
- 조건 미충족: 마스킹 유지

정책:
- 원본 JSON에는 원본 파일명 유지
- 마크다운 리포트: 기본 마스킹
- 로컬 UI: 사용자 인증 후 원본 표시 가능
- 서버/AI 전송: 기본 마스킹 유지
"""
from __future__ import annotations

import re


class PrivacyMasker:
    """민감 파일명 마스킹기.

    정책:
    - 강한 민감 패턴: 신분증, 통장사본, 형사사건, 고소, 소송, 증거 등 → 항상 마스킹
    - 약한 민감 패턴: 계약서 단독 → 마스킹하지 않음
    - 조합 패턴: 계약서 + (신분증|계좌|급여|형사|소송|변호인) → 마스킹
    - 제외: 소프트웨어 설치파일, ISO, CAB 등
    """

    # 강한 민감 패턴 (항상 마스킹)
    STRONG_SENSITIVE_PATTERNS = {
        # 증명서/신분증류
        r"신분증": "[신분증]",
        r"주민등록증": "[주민등록증]",
        r"운전면허": "[운전면허]",
        r"여권": "[여권]",
        # 금융/계좌
        r"통장.*사본": "[통장사본]",
        r"계좌": "[계좌]",
        r"금통": "[금융]",
        r"은행": "[은행]",
        # 법률 문서 (강한)
        r"형사.*사건": "[형사사건]",
        r"고소": "[고소]",
        r"소송": "[소송]",
        r"변호인.*의견": "[법률문서]",
        # 기타 민감 정보
        r"개인정보": "[개인정보]",
        r"급여": "[급여]",
        r"노임": "[급여]",
        r"증거": "[증거]",
        r"기밀": "[기밀]",
    }

    # 약한 민감 패턴 (조합 시에만 마스킹)
    WEAK_SENSITIVE_PATTERNS = {
        r"계약서": "[계약서]",
        r"변호사": "[법률]",
        r"합의금": "[계약]",
    }

    # 제외 패턴 (마스킹하지 않음)
    EXCLUDE_PATTERNS = {
        r"한컴오피스",
        r"hwp",
        r"hancom",
        r"마이크로소프트.*오피스",
        r"microsoft.*office",
        r"office",
        r"autocad",
        r"\.iso$",
        r"\.cab$",
        r"installer",
        r"setup",
        r"\.msi$",
        r"\.exe$",
    }

    @staticmethod
    def render_filename(
        filename: str,
        reveal_sensitive_names: bool = False,
        auth_verified: bool = False,
    ) -> str:
        """파일명을 표시 정책에 따라 렌더링한다.

        Args:
            filename: 원본 파일명
            reveal_sensitive_names: 민감 파일명 표시 활성화 여부
            auth_verified: 사용자 본인 인증 완료 여부

        Returns:
            렌더링된 파일명

        정책 (AND 로직):
            - reveal_sensitive_names=False OR auth_verified=False → 마스킹
            - reveal_sensitive_names=True AND auth_verified=True → 원본 표시
        """
        # AND 로직: 둘 다 True여야 원본 표시
        if reveal_sensitive_names and auth_verified:
            return filename

        # 그 외의 경우: 마스킹
        return PrivacyMasker.mask_filename(filename)

    @staticmethod
    def mask_filename(filename: str) -> str:
        """민감 파일명을 마스킹한다.

        정책:
        1. 제외 패턴 확인: 소프트웨어 설치파일 등은 그대로 반환
        2. 강한 민감 패턴: 항상 마스킹
        3. 약한 민감 패턴: 강한 패턴과 조합할 때만 마스킹
        4. 개인명: 2-4글자 한글 마스킹

        Args:
            filename: 원본 파일명

        Returns:
            마스킹된 파일명
        """
        if not filename:
            return filename

        # 1. 제외 패턴 확인 (설치파일 등)
        for pattern in PrivacyMasker.EXCLUDE_PATTERNS:
            if re.search(pattern, filename, re.IGNORECASE):
                return filename  # 마스킹하지 않음

        masked = filename

        # 2. 강한 민감 패턴 마스킹 (항상)
        for pattern, replacement in PrivacyMasker.STRONG_SENSITIVE_PATTERNS.items():
            masked = re.sub(
                pattern,
                replacement,
                masked,
                flags=re.IGNORECASE
            )

        # 3. 약한 민감 패턴 처리 (조합 확인)
        # 약한 패턴이 강한 패턴과 함께 있으면 마스킹
        has_strong = any(
            re.search(pattern, filename, re.IGNORECASE)
            for pattern in PrivacyMasker.STRONG_SENSITIVE_PATTERNS.keys()
        )

        if has_strong:
            # 강한 패턴이 있으면 약한 패턴도 마스킹
            for pattern, replacement in PrivacyMasker.WEAK_SENSITIVE_PATTERNS.items():
                masked = re.sub(
                    pattern,
                    replacement,
                    masked,
                    flags=re.IGNORECASE
                )

            # 개인명도 마스킹 (강한 패턴이 있을 때만)
            masked = re.sub(
                r"[가-힣]{2,4}(?=[\s_])",
                "****",
                masked
            )

        return masked

    @staticmethod
    def mask_path(
        path: str,
        reveal_sensitive_names: bool = False,
        auth_verified: bool = False,
    ) -> str:
        """경로에서 파일명만 마스킹한다.

        Args:
            path: 전체 파일 경로
            reveal_sensitive_names: 민감 파일명 표시 활성화 여부
            auth_verified: 사용자 본인 인증 완료 여부

        Returns:
            마스킹된 경로 또는 원본 경로
        """
        if not path:
            return path

        # AND 로직: 둘 다 True여야 원본 표시
        if not (reveal_sensitive_names and auth_verified):
            # 마스킹 모드
            for sep in ["\\", "/"]:
                if sep in path:
                    parts = path.rsplit(sep, 1)
                    if len(parts) == 2:
                        dir_part, filename = parts
                        masked_filename = PrivacyMasker.mask_filename(filename)
                        return f"{dir_part}{sep}{masked_filename}"

            # 경로 구분자 없음 (파일명만)
            return PrivacyMasker.mask_filename(path)

        # 원본 모드
        return path

    @staticmethod
    def should_mask(filename: str) -> bool:
        """파일명이 마스킹 대상인지 확인.

        Args:
            filename: 파일명

        Returns:
            마스킹 대상 여부
        """
        # 제외 패턴이면 마스킹 대상 아님
        for pattern in PrivacyMasker.EXCLUDE_PATTERNS:
            if re.search(pattern, filename, re.IGNORECASE):
                return False

        # 강한 민감 패턴이면 마스킹 대상
        for pattern in PrivacyMasker.STRONG_SENSITIVE_PATTERNS.keys():
            if re.search(pattern, filename, re.IGNORECASE):
                return True

        # 약한 패턴은 강한 패턴과 조합일 때만
        has_weak = any(
            re.search(pattern, filename, re.IGNORECASE)
            for pattern in PrivacyMasker.WEAK_SENSITIVE_PATTERNS.keys()
        )
        if has_weak:
            has_strong = any(
                re.search(pattern, filename, re.IGNORECASE)
                for pattern in PrivacyMasker.STRONG_SENSITIVE_PATTERNS.keys()
            )
            if has_strong:
                return True

        return False
