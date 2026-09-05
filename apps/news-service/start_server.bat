@echo off
cd /d "%~dp0"

REM 停掉旧的 server（如果有）
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8888 "') do (
    taskkill /PID %%a /F >nul 2>&1
)

REM 后台启动（最小化窗口）
start "" /min python server.py 8888
echo Server started: http://127.0.0.1:8888
