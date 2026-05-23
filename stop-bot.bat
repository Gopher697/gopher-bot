@echo off
title Bot Shutdown
echo ============================================================
echo   Shutting down...
echo ============================================================
echo.

echo Stopping Neo4j database...
taskkill /FI "WINDOWTITLE eq Neo4j DB" /T /F >nul 2>&1

echo Stopping Python backend...
taskkill /FI "WINDOWTITLE eq Bot Backend" /T /F >nul 2>&1

echo Stopping avatar...
taskkill /IM "gopher-bot-avatar.exe" /T /F >nul 2>&1

echo.
echo Done. Bot is offline.
pause
