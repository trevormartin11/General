@echo off
REM Double-click (Windows): opens the draft co-pilot in its own window.
cd /d "%~dp0"
where py >nul 2>&1 && (py draft.py live %*) || (python draft.py live %*)
echo.
pause
