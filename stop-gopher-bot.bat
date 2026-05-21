@echo off
title Gopher-bot Shutdown
echo ============================================================
echo   Gopher-bot -- Shutting down...
echo ============================================================
echo.

echo Stopping Python backend...
taskkill /FI "WINDOWTITLE eq Gopher-bot Backend" /T /F >nul 2>&1

echo Stopping avatar...
taskkill /IM "gopher-bot-avatar.exe" /T /F >nul 2>&1

echo.
echo Done. Gopher-bot is offline.
pause
