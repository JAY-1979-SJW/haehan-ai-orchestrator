HaehanAI Desktop Portable ZIP 실행 방법
======================================

현재 1차 공식 배포 방식은 installer exe가 아니라 Portable ZIP + install.bat 방식입니다.
installer exe 방식은 현재 보류 중입니다.

1. ZIP 압축 해제
---------------
ZIP 파일을 원하는 폴더에 압축 해제합니다.
예: 바탕화면, 다운로드 폴더, 문서 폴더

Program Files로 복사할 필요가 없습니다.
관리자 권한으로 실행할 필요가 없습니다.

2. 설치
-------
압축을 푼 폴더에서 install.bat을 실행합니다.

install.bat은 다음 작업만 수행합니다.
- 현재 폴더 기준으로 실행 경로를 인식합니다.
- logs 폴더와 config 폴더를 만듭니다.
- 바탕화면에 "HaehanAI Desktop" 바로가기를 만듭니다.

install.bat은 다음 작업을 하지 않습니다.
- Program Files에 복사하지 않습니다.
- registry를 수정하지 않습니다.
- PATH를 수정하지 않습니다.
- 서버나 Docker를 실행하지 않습니다.

3. 실행
-------
바탕화면의 "HaehanAI Desktop" 바로가기를 실행하거나,
압축을 푼 폴더에서 start.bat을 실행합니다.

start.bat은 현재 폴더에서 HaehanAI-Desktop.exe를 찾아 실행합니다.
실행 파일을 찾지 못하면 diagnostics.bat 실행을 안내합니다.

4. 진단
-------
문제가 있으면 diagnostics.bat을 실행합니다.

diagnostics.bat은 필수 파일, logs/config 폴더, 8765 포트 상태, 일부 환경 변수의 존재 여부를 점검합니다.
secret, token, password, API key의 원문 값은 출력하지 않습니다.

진단 결과는 다음 형식으로 저장됩니다.
logs\diagnostics_YYYYMMDD_HHMMSS.txt

5. 삭제
-------
uninstall.bat을 실행하면 바탕화면 바로가기만 제거합니다.

uninstall.bat은 앱 폴더, logs 폴더, config 폴더를 삭제하지 않습니다.
앱 파일까지 삭제하려면 프로그램을 종료한 뒤 압축을 푼 폴더를 직접 삭제하면 됩니다.

6. 오류 발생 시 복구
-------------------
실행이 되지 않거나 바로가기가 깨진 경우:
1. diagnostics.bat을 실행합니다.
2. logs\diagnostics_YYYYMMDD_HHMMSS.txt 파일을 확인합니다.
3. 바탕화면 바로가기 문제이면 uninstall.bat을 실행한 뒤 install.bat을 다시 실행합니다.

HaehanAI-Desktop.exe 파일이 없다고 나오면:
1. ZIP 파일을 새 폴더에 다시 압축 해제합니다.
2. 새 폴더에서 install.bat을 다시 실행합니다.

port_8765=in_use가 나오면:
1. 이미 실행 중인 HaehanAI Desktop 창을 종료합니다.
2. 그래도 해결되지 않으면 PC를 재부팅한 뒤 start.bat을 다시 실행합니다.

설정 문제를 초기화해야 하는 경우:
- uninstall.bat은 logs/config를 삭제하지 않습니다.
- config 폴더를 삭제해야 한다면 먼저 백업한 뒤 사용자가 직접 삭제합니다.
- logs 폴더는 진단 기록이므로 자동 삭제하지 않습니다.

개발/릴리스 전 복구 검증:
- 정적 검증: python verify_portable_zip_install.py --static-only
- 전체 sandbox 검증: python verify_portable_zip_install.py
- 회귀 테스트: python -m pytest tests\test_portable_zip_install_contract.py -q
