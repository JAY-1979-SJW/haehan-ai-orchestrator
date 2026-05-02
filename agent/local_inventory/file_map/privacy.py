"""민감 파일명 마스킹.

상용 리포트용 민감한 파일명을 마스킹하는 기능.
원본 JSON에는 원본 파일명을 유지하고, 마크다운 리포트에만 마스킹 적용.
"""
from __future__ import annotations

import re


class PrivacyMasker:
    """민감 파일명 마스킹기."""

    # 민감 패턴
    SENSITIVE_PATTERNS = {
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
        # 법률 문서
        r"형사.*사건": "[형사사건]",
        r"고소": "[고소]",
        r"변호인.*의견": "[법률문서]",
        r"변호사": "[법률]",
        r"합의금": "[계약]",
        r"소송": "[소송]",
        # 기타 민감 정보
        r"개인정보": "[개인정보]",
        r"급여\|노임": "[급여]",
        r"증거": "[증거]",
        r"기밀": "[기밀]",
    }

    @staticmethod
    def mask_filename(
        filename: str,
        reveal_sensitive: bool = False
    ) -> str:
        """민감 파일명을 마스킹한다.

        Args:
            filename: 원본 파일명
            reveal_sensitive: True면 원본 유지, False면 마스킹

        Returns:
            마스킹된 파일명 또는 원본 파일명
        """
        if reveal_sensitive or not filename:
            return filename

        masked = filename

        # 민감 패턴 매칭 및 마스킹
        for pattern, replacement in PrivacyMasker.SENSITIVE_PATTERNS.items():
            # 대소문자 구분 없이 매칭
            masked = re.sub(
                pattern,
                replacement,
                masked,
                flags=re.IGNORECASE
            )

        # 개인명 마스킹: 2-4글자 한글을 **로 치환
        # 예: 곽영규_통장사본.jpg → ****_통장사본.jpg
        # 또는: 권명수_통장사본.pdf → ****_통장사본.pdf
        masked = re.sub(
            r"[가-힣]{2,4}(?=[\s_])",  # 2-4글자 한글 + 언더스코어/공백 미리보기
            "****",
            masked
        )

        return masked

    @staticmethod
    def mask_path(
        path: str,
        reveal_sensitive: bool = False
    ) -> str:
        """경로에서 파일명만 마스킹한다.

        Args:
            path: 전체 파일 경로
            reveal_sensitive: True면 원본 유지

        Returns:
            마스킹된 경로
        """
        if reveal_sensitive or not path:
            return path

        # 마지막 경로 구분자 찾기
        for sep in ["\\", "/"]:
            if sep in path:
                parts = path.rsplit(sep, 1)
                if len(parts) == 2:
                    dir_part, filename = parts
                    masked_filename = PrivacyMasker.mask_filename(
                        filename,
                        reveal_sensitive
                    )
                    return f"{dir_part}{sep}{masked_filename}"

        # 경로 구분자 없음 (파일명만)
        return PrivacyMasker.mask_filename(path, reveal_sensitive)

    @staticmethod
    def should_mask(filename: str) -> bool:
        """파일명이 마스킹 대상인지 확인.

        Args:
            filename: 파일명

        Returns:
            마스킹 대상 여부
        """
        for pattern in PrivacyMasker.SENSITIVE_PATTERNS.keys():
            if re.search(pattern, filename, re.IGNORECASE):
                return True
        return False
