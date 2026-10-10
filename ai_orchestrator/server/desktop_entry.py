"""데스크톱 앱 번들(PyInstaller haehan-server) 진입점.

PyInstaller 는 진입 파일을 패키지 밖의 단독 스크립트(__main__)로 실행한다. ai_orchestrator/asgi.py 를
그대로 진입점으로 쓰면 그 안의 상대 import(`from . import config`)가 "no known parent package" 로
실패해 서버가 시작되지 않는다(2026-10-08 첫 빌드 E2E 실측: fastapi.log ImportError). 이 파일은
상대 import 없이 패키지 경로로 asgi 를 불러 uvicorn 을 띄운다.
"""

import uvicorn

from ai_orchestrator import asgi


def main() -> None:
    uvicorn.run(asgi.app, host=asgi.APP_HOST, port=asgi.APP_PORT, reload=False)


if __name__ == "__main__":
    main()
