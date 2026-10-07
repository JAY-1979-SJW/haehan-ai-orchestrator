"""네이버 MyBox Mixin — auto_structure_builder 자동 생성."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any


def _js(name: str) -> str:
    from scripts.common.browser_js_dir import JS_DIR

    return (JS_DIR / name).read_text(encoding="utf-8")


class MyBoxMixin:
    """네이버 MyBox 기능.

    실제 캡처된 API: ['/api/v1/pay/users/status', '/jsonp/push/count/v2/services/chat', '/api/general/config', '/service/user/get', '/api/v1/pay/users/status']
    """

    if TYPE_CHECKING:
        # 다른 믹스인의 메서드·속성(go, _page …)을 self(MRO)로 쓴다 — 정적 검사기에는 합쳐진 클래스가 보이지 않으므로 알려 준다(런타임 영향 없음).
        def __getattr__(self, name: str) -> Any: ...

    def mybox_list(self, path: str = "/") -> list[dict]:
        """파일/폴더 목록 — file/get + file/list 2단계 호출.

        Note: 현재 path는 "/" (root)만 지원. 하위 폴더 진입은 추후 확장.
        반환: [{name, type, size, mtime, resource_key}]
        """
        self.go("https://mybox.naver.com/main/web/my")
        time.sleep(3)

        try:
            data = self._page.evaluate("""async () => {
                // 1단계: root 정보 조회
                const r1 = await fetch('https://api.mybox.naver.com/service/file/get?resourceKey=root', { credentials: 'include' });
                if (!r1.ok) return { error: 'get failed', status: r1.status };
                const j1 = await r1.json();
                const rk = j1?.result?.resourceKey;
                if (!rk) return { error: 'no resourceKey', json: j1 };

                // 2단계: 파일 리스트 조회
                const r2 = await fetch('https://api.mybox.naver.com/service/file/list?resourceKey=' + encodeURIComponent(rk), { credentials: 'include' });
                if (!r2.ok) return { error: 'list failed', status: r2.status };
                return await r2.json();
            }""")
            if not data or data.get("code") != "0":
                return []
            result = data.get("result", {})
            raw = result.get("list", [])
            if not isinstance(raw, list):
                return []
            return [
                {
                    "name": f.get("resourcePath", "").lstrip("/").split("/")[-1] or f.get("name", ""),
                    "type": f.get("resourceType", "file"),
                    "size": f.get("resourceSize", 0),
                    "mtime": f.get("updateDate", 0),
                    "resource_key": f.get("resourceKey", ""),
                }
                for f in raw
            ]
        except Exception:  # noqa: BLE001 - 네이버 마이박스 파일 목록/용량 조회 -- 읽기 전용 JSON API, 실패 시 빈 리스트/딕셔너리 반환
            return []

    def mybox_quota(self) -> dict:
        """용량 정보 조회 — JSON API.

        반환: {used, total, unused, file_max, unit}
        단위는 bytes
        """
        self.go("https://mybox.naver.com/main/web/my")
        time.sleep(3)
        try:
            data = self._page.evaluate("""async () => {
                const resp = await fetch('https://api.mybox.naver.com/service/quota/get', { credentials: 'include' });
                if (!resp.ok) return null;
                return await resp.json();
            }""")
            if not data or data.get("code") != "0":
                return {}
            result = data.get("result", {})
            return {
                "used": result.get("usedQuota", 0),
                "total": result.get("totalQuota", 0),
                "unused": result.get("unusedQuota", 0),
                "file_max": result.get("fileMaxSize", 0),
                "unit": "bytes",
            }
        except Exception:  # noqa: BLE001 - 네이버 마이박스 파일 목록/용량 조회 -- 읽기 전용 JSON API, 실패 시 빈 리스트/딕셔너리 반환
            return {}
