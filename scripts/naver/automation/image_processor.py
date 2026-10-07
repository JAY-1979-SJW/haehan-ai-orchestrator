"""이미지 자동 처리 — 리사이즈/포맷/워터마크/배경.

스마트스토어 권장 이미지: 1000x1000 정사각, JPG/PNG, 10MB 이하.

기능:
  - 자동 리사이즈 (긴 변 기준)
  - 정사각 패딩 (white background)
  - JPG 변환 + 품질 최적화
  - 워터마크 텍스트/로고 추가
  - 일괄 처리 (디렉토리)

요구: pip install Pillow
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.common.critical_logger import log_critical
from scripts.common.logger import get_logger

_log = get_logger(__name__)


class ImageProcessor:
    """상품 이미지 일괄 처리."""

    def __init__(self):
        try:
            from PIL import Image

            self._PIL = Image
        except ImportError:
            self._PIL = None
            _log.warning("[image] Pillow 미설치 — pip install Pillow")

    def _ensure_pil(self) -> bool:
        if self._PIL is None:
            return False
        return True

    def resize(self, src: str, dst: str, max_side: int = 1000, square: bool = True, quality: int = 90) -> dict:
        """이미지 리사이즈 + 정사각 패딩."""
        if not self._ensure_pil():
            return {"ok": False, "error": "pillow_not_installed"}
        src_path = Path(src)
        if not src_path.exists():
            return {"ok": False, "error": "src_not_found"}

        try:
            img = self._PIL.open(src).convert("RGB")
            # 비율 유지 리사이즈
            img.thumbnail((max_side, max_side), self._PIL.Resampling.LANCZOS)

            if square:
                # 흰색 정사각 배경에 가운데 배치
                bg = self._PIL.new("RGB", (max_side, max_side), (255, 255, 255))
                off_x = (max_side - img.width) // 2
                off_y = (max_side - img.height) // 2
                bg.paste(img, (off_x, off_y))
                img = bg

            dst_path = Path(dst)
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(dst_path, "JPEG", quality=quality, optimize=True)

            size_kb = dst_path.stat().st_size // 1024
            return {"ok": True, "src": src, "dst": dst, "size_kb": size_kb, "dimensions": [img.width, img.height]}
        except Exception as e:  # noqa: BLE001 - 이미지 리사이즈/워터마크 처리 유틸 — 처리 실패 시 ok=False와 에러 메시지를 담은 dict 반환, 폰트 로드 실패 시 기본 폰트로 폴백할 뿐 파일 삭제 없음
            return {"ok": False, "error": str(e)[:80]}

    def add_watermark(
        self, src: str, dst: str, text: str, position: str = "bottom-right", opacity: float = 0.5, font_size: int = 24
    ) -> dict:
        """텍스트 워터마크 추가."""
        if not self._ensure_pil():
            return {"ok": False, "error": "pillow_not_installed"}
        try:
            from PIL import ImageDraw, ImageFont

            img = self._PIL.open(src).convert("RGBA")
            overlay = self._PIL.new("RGBA", img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)
            try:
                font = ImageFont.truetype("malgun.ttf", font_size)
            except Exception:  # noqa: BLE001 - 이미지 리사이즈/워터마크 처리 유틸 — 처리 실패 시 ok=False와 에러 메시지를 담은 dict 반환, 폰트 로드 실패 시 기본 폰트로 폴백할 뿐 파일 삭제 없음
                font = ImageFont.load_default()
            # 텍스트 위치 계산
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            positions = {
                "top-left": (10, 10),
                "top-right": (img.width - tw - 10, 10),
                "bottom-left": (10, img.height - th - 10),
                "bottom-right": (img.width - tw - 10, img.height - th - 10),
                "center": ((img.width - tw) // 2, (img.height - th) // 2),
            }
            x, y = positions.get(position, positions["bottom-right"])
            alpha = int(255 * opacity)
            draw.text((x, y), text, fill=(255, 255, 255, alpha), font=font)

            combined = self._PIL.alpha_composite(img, overlay).convert("RGB")
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            combined.save(dst, "JPEG", quality=90, optimize=True)
            return {"ok": True, "dst": dst, "watermark": text, "position": position}
        except Exception as e:  # noqa: BLE001 - 이미지 리사이즈/워터마크 처리 유틸 — 처리 실패 시 ok=False와 에러 메시지를 담은 dict 반환, 폰트 로드 실패 시 기본 폰트로 폴백할 뿐 파일 삭제 없음
            return {"ok": False, "error": str(e)[:80]}

    def batch_process(
        self, src_dir: str, dst_dir: str, max_side: int = 1000, square: bool = True, watermark: str | None = None
    ) -> dict:
        """디렉토리 일괄 처리."""
        if not self._ensure_pil():
            return {"ok": False, "error": "pillow_not_installed"}
        src = Path(src_dir)
        dst = Path(dst_dir)
        if not src.exists():
            return {"ok": False, "error": "src_dir_not_found"}

        exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
        files = [f for f in src.rglob("*") if f.suffix.lower() in exts]
        results: list[dict[str, Any]] = []
        for f in files:
            out = dst / (f.stem + ".jpg")
            r1 = self.resize(str(f), str(out), max_side=max_side, square=square)
            if r1.get("ok") and watermark:
                r2 = self.add_watermark(str(out), str(out), watermark)
                r1["watermark"] = r2
            results.append({"src": str(f), "result": r1})
        ok = sum(1 for r in results if r["result"].get("ok"))
        log_critical(
            "OTHER", f"이미지 일괄 처리: {ok}/{len(files)}", src_dir=src_dir, dst_dir=dst_dir, mode="image_batch"
        )
        return {"ok": ok == len(files), "total": len(files), "success": ok, "results": results}
