@echo off
REM Double-click (Windows): runs an offline practice draft in this window. Enter = take the #1 pick.
cd /d "%~dp0"
where py >nul 2>&1 && (py draft.py mock %*) || (python draft.py mock %*)
echo.
pause
