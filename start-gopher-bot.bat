@echo off
title Gopher-bot Launcher
cd /d "%~dp0"

echo ============================================================
echo   Gopher-bot -- Starting up...
echo ============================================================
echo.

:: -- Neo4j ----------------------------------------------------
:: Launch Neo4j Desktop (it resumes the last running database automatically)
:: Auto-detect install path from registry, then fall back to common locations.
echo [0/2] Launching Neo4j Desktop...
set NEO4J_DESKTOP=
:: Search all HKCU uninstall entries for anything with "Neo4j" in the name
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' | Where-Object { $_.DisplayName -like '*Neo4j*' } | Select-Object -ExpandProperty DisplayIcon -EA SilentlyContinue | Select-Object -First 1 | ForEach-Object { $_ -replace ',\d+$','' }"`) do set NEO4J_DESKTOP=%%a
if not defined NEO4J_DESKTOP (
    for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' | Where-Object { $_.DisplayName -like '*Neo4j*' } | Select-Object -ExpandProperty DisplayIcon -EA SilentlyContinue | Select-Object -First 1 | ForEach-Object { $_ -replace ',\d+$','' }"`) do set NEO4J_DESKTOP=%%a
)
:: Common Squirrel install locations as final fallback
if not defined NEO4J_DESKTOP (
    if exist "%LOCALAPPDATA%\Programs\neo4j-desktop\Neo4j Desktop.exe" set NEO4J_DESKTOP=%LOCALAPPDATA%\Programs\neo4j-desktop\Neo4j Desktop.exe
)
if not defined NEO4J_DESKTOP (
    if exist "%LOCALAPPDATA%\neo4j-desktop\Neo4j Desktop.exe" set NEO4J_DESKTOP=%LOCALAPPDATA%\neo4j-desktop\Neo4j Desktop.exe
)

:: Try to start the DBMS directly via neo4j.bat (finds bundled JRE automatically)
set DBMS_DIR=C:\Users\gophe\.Neo4jDesktop2\Data\dbmss\dbms-54750ef6-52b6-4e69-b36e-2920fb10a8db
set NEO4J_BAT=%DBMS_DIR%\bin\neo4j.bat
set JAVA_EXE=
if exist "%NEO4J_BAT%" (
    for /r "%USERPROFILE%\.Neo4jDesktop2\Cache" %%j in (java.exe) do if not defined JAVA_EXE set JAVA_EXE=%%j
)
if defined JAVA_EXE (
    for %%j in ("%JAVA_EXE%") do set "JAVA_HOME=%%~dpj"
    :: JAVA_HOME should be the jre root (parent of bin\)
    set "JAVA_HOME=%JAVA_HOME:~0,-5%"
    echo     Found JRE at: %JAVA_HOME%
    call "%NEO4J_BAT%" start >nul 2>&1
    echo     Neo4j database process started directly.
) else if defined NEO4J_DESKTOP (
    :: Fall back to opening Desktop and letting user start DB manually
    start "" "%NEO4J_DESKTOP%"
    echo     Launched: %NEO4J_DESKTOP%
    echo     [NOTE] Click 'Start' on gopher-bot-data in Neo4j Desktop.
) else (
    echo [WARN] Could not start Neo4j automatically. Start your database manually, then press any key.
    pause
)

:: Wait for Neo4j to be reachable on port 7687 (up to 60 seconds)
echo     Waiting for Neo4j on port 7687...
set /a _tries=0
:neo4j_wait
set /a _tries+=1
powershell -Command "try { $t = New-Object Net.Sockets.TcpClient('localhost', 7687); $t.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 (
    echo     [OK] Neo4j is running.
    goto neo4j_ready
)
if %_tries% geq 30 (
    echo     [WARN] Neo4j did not start after 60 seconds. Continuing anyway...
    goto neo4j_ready
)
timeout /t 2 /nobreak >nul
goto neo4j_wait
:neo4j_ready
echo.

:: -- Python backend -------------------------------------------
echo [1/2] Starting Python backend...
start "Gopher-bot Backend" /min cmd /c "cd /d %~dp0 && python interface/server.py & pause"

echo     Waiting for server to initialize...
timeout /t 4 /nobreak >nul

:: -- Godot avatar ---------------------------------------------
echo [2/2] Launching avatar...
set AVATAR_EXE=%~dp0avatar\export\gopher-bot-avatar.exe
if exist "%AVATAR_EXE%" (
    start "" "%AVATAR_EXE%"
    echo     Avatar launched.
) else (
    echo [WARN] Avatar exe not found at: %AVATAR_EXE%
    echo       Export it from Godot: Project ^> Export ^> Export Project
)

echo.
echo ============================================================
echo   Gopher-bot is running.
echo   Backend: minimized window "Gopher-bot Backend"
echo   Avatar:  floating on your desktop
echo   Web UI:  http://localhost:5000
echo   Run stop-gopher-bot.bat to shut everything down.
echo ============================================================
echo.
pause
