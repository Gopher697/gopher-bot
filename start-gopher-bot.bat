@echo off
cd /d "%~dp0"
echo Starting Gopher-bot...
python interface/server.py
pause
