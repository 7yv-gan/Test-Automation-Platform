@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   自动化测试平台 一键启动
echo   访问地址: http://127.0.0.1:8000
echo   默认账号: admin / admin123
echo   关闭本窗口即停止服务
echo ============================================
set "PY=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
%PY% main.py
pause
