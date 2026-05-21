@echo off
title Gopher-bot Launcher
cd /d "%~dp0"

echo ============================================================
echo   Gopher-bot -- Starting up...
echo ============================================================
echo.

:: -- Neo4j ----------------------------------------------------
echo [0/2] Launching Neo4j Desktop...
set NEO4J_DESKTOP=

:: Search registry for Neo4j Desktop (HKCU first, then HKLM)
for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' | Where-Object { $_.DisplayName -like '*Neo4j*' } | Select-Object -ExpandProperty DisplayIcon -EA SilentlyContinue | Select-Object -First 1 | ForEach-Object { $_ -replace ',\d+$','' }"`) do set NEO4J_DESKTOP=%%a
if not defined NEO4J_DESKTOP (
    for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' | Where-Object { $_.DisplayName -like '*Neo4j*' } | Select-Object -ExpandProperty DisplayIcon -EA SilentlyContinue | Select-Object -First 1 | ForEach-Object { $_ -replace ',\d+$','' }"`) do set NEO4J_DESKTOP=%%a
)
if not defined NEO4J_DESKTOP (
    if exist "C:\Program Files\Neo4j Desktop 2\Neo4j Desktop.exe" set "NEO4J_DESKTOP=C:\Program Files\Neo4j Desktop 2\Neo4j Desktop.exe"
)
if not defined NEO4J_DESKTOP (
    if exist "%LOCALAPPDATA%\Programs\neo4j-desktop\Neo4j Desktop.exe" set "NEO4J_DESKTOP=%LOCALAPPDATA%\Programs\neo4j-desktop\Neo4j Desktop.exe"
)

:: Always open Neo4j Desktop (useful for monitoring even if we start DB directly)
if defined NEO4J_DESKTOP (
    start "" "%NEO4J_DESKTOP%"
    echo     Launched Neo4j Desktop: %NEO4J_DESKTOP%
) else (
    echo     [WARN] Neo4j Desktop not found.
)

:: Auto-start the DBMS via neo4j.bat.
:: Priority: (1) system JAVA_HOME set by Temurin/OpenJDK installer,
::           (2) JRE bundled in Neo4j Desktop Cache (fallback).
:: We never override a system JAVA_HOME — if it's already set and valid, use it as-is.
set DBMS_DIR=C:\Users\gophe\.Neo4jDesktop2\Data\dbmss\dbms-54750ef6-52b6-4e69-b36e-2920fb10a8db
set NEO4J_BAT=%DBMS_DIR%\bin\neo4j.bat

:: 1) System Java (Temurin 21 etc.) — JAVA_HOME already in environment
if defined JAVA_HOME (
    if exist "%JAVA_HOME%\bin\java.exe" (
        echo     Using system Java: %JAVA_HOME%
        goto start_neo4j_bat
    )
)

:: 2) Cache JRE fallback — compute JAVA_HOME from bundled JRE path
set JAVA_EXE=
set CACHE_ROOT=%USERPROFILE%\.Neo4jDesktop2\Cache
if exist "%NEO4J_BAT%" (
    for /f "usebackq delims=" %%a in (`powershell -NoProfile -Command "Get-ChildItem -Path '%CACHE_ROOT%' -Filter java.exe -Recurse -Depth 8 -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName"`) do set JAVA_EXE=%%a
)
if not defined JAVA_EXE goto no_jre
for %%j in ("%JAVA_EXE%") do set "JAVA_HOME=%%~dpj"
set "JAVA_HOME=%JAVA_HOME:~0,-5%"
echo     Found Cache JRE at: %JAVA_HOME%

:start_neo4j_bat
if not exist "%NEO4J_BAT%" goto no_jre
echo     Starting Neo4j database directly...
cmd /c ""%NEO4J_BAT%" start"
if %errorlevel% neq 0 (
    echo     [NOTE] neo4j.bat returned an error. Start DB manually in Neo4j Desktop.
) else (
    echo     Neo4j database process started.
)
goto neo4j_wait

:no_jre
echo     [NOTE] No Java found. Click 'Start' on gopher-bot-data in Neo4j Desktop.

:: Wait for Neo4j to be reachable on port 7687 (up to 60 seconds)
:neo4j_wait
echo     Waiting for Neo4j on port 7687...
set /a _tries=0
:neo4j_poll
set /a _tries+=1
powershell -Command "try { $t = New-Object Net.Sockets.TcpClient('localhost', 7687); $t.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel%==0 (
    echo     [OK] Neo4j is running.
    goto neo4j_ready
)
if %_tries% geq 30 (
    echo     [WARN] Neo4j not reachable after 60 seconds. Proceeding...
    goto neo4j_ready
)
timeout /t 2 /nobreak >nul
goto neo4j_poll
:neo4j_ready
echo.

:: -- Python backend -------------------------------------------
echo [1/2] Starting Python backend...
start "Gopher-bot Backend" /min cmd /c "cd /d %~dp0 && python interface/server.py & pause"

echo     Waiting for server to initialize...
timeout /t 4 /nobreak >nul

:: -- World Map ------------------------------------------------
echo [1.5/2] Launching world map...
start "" python "%~dp0interface\world_map.py"
timeout /t 2 /nobreak >nul

:: -- Godot avatar ---------------------------------------------
echo [2/2] Launching avatar...
set AVATAR_EXE=%~dp0avatar\export\gopher-bot-avatar.exe
if exist "%AVATAR_EXE%" (
    start "" "%AVATAR_EXE%"
    echo     Avatar launched.
) else (
    echo [WARN] Avatar exe not found at: %AVATAR_EXE%
    echo       Export from Godot: Project ^> Export ^> Export Project
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
