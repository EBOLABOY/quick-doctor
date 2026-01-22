@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 正在启动 91160 抢号助手 (GUI版)...
if exist ".venv\Scripts\python.exe" (
    start "" .venv\Scripts\pythonw.exe main_gui.py
) else (
    echo [ERROR] 虚拟环境未找到，请先运行 run.bat 完成环境安装
    pause
)
