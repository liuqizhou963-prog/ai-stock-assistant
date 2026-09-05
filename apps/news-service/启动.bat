@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM 检查服务是否已在运行
netstat -an 2>nul | findstr ":8888.*LISTENING" >nul
if %errorlevel%==0 (
    start "" "http://localhost:8888"
    exit /b
)

REM 后台启动服务（最小化窗口）
start /min "资讯助手" python server.py

REM 等待服务就绪
timeout /t 3 /noisy >nul

REM 打开浏览器
start "" "http://localhost:8888"
