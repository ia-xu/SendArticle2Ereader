@echo off
chcp 65001 >nul
echo ========================================
echo   Markdown to KFX Converter WebUI
echo ========================================
echo.
echo Starting server...
echo.
cd /d "%~dp0"
conda activate anxu && python webui\app.py
pause