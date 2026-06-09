@echo off
set AUTH_ENABLED=false
set HAEHAN_PORT=8401
set HAEHAN_HOST=127.0.0.1
cd /d "C:\work\01. haehan-ai-orchestrator\dist-installer\win-unpacked\resources\server\haehan-server"
start "" haehan-server.exe
