@echo off
title Bot Launcher
cd /d "%~dp0"

echo ============================================================
echo   Starting up...
echo ============================================================
echo.

:: -- Neo4j ----------------------------------------------------
:: Auto-start the DBMS via neo4j.bat.
:: Priority: (1) system JAVA_HOME set by Temurin/OpenJDK installer,
::           (2) JRE bundled in Neo4j Desktop Cache (fallback).
:: We never override a system JAVA_HOME — if it's already set and valid, use it as-is.
:: Set this to your Neo4j DBMS directory.
:: Find it in Neo4j Desktop: click the three-dot menu on your DBMS → "Open Folder" → "DBMS"
set DBMS_DIR=C:\Users\gophe\.Neo4jDesktop2\Data\dbmss\dbms-54750ef6-52b6-4e69-b36e-2920fb10a8db
set NEO4J_BAT=%DBMS_DIR%\bin\neo4j.bat

:: 1) System Java (Temurin 21 etc.) — JAVA_HOME already in environment
:: Note: goto inside nested parenthesized if-blocks crashes cmd.exe (parse-time issue).
:: Use a flag variable so the goto happens at the top level.
set _USE_SYS_JAVA=0
if defined JAVA_HOME (
    if exist "%JAVA_HOME%\bin\java.exe" set _USE_SYS_JAVA=1
)
if %_USE_SYS_JAVA%==1 (
    echo     Using system Java: %JAVA_HOME%
    goto start_neo4j_bat
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
echo     Starting Neo4j database (console mode)...
start "Neo4j DB" /min cmd /c ""%NEO4J_BAT%" console"
echo     Neo4j process launched (minimized).
goto neo4j_wait

:no_jre
echo     [NOTE] DBMS path not configured or Java not found. Start your DBMS manually in Neo4j Desktop.

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

:: -- Schema migrations ---------------------------------------
echo [1.5/2] Running database migrations...
python "%~dp0scripts\run_migrations.py"
if %errorlevel% neq 0 (
    echo     [ERROR] Migration failed. Check Neo4j is running and config is correct.
    pause
    exit /b 1
)
echo     [OK] Schema up to date.
echo.

:: -- Health check --------------------------------------------
echo [1.75/2] Running health check...
python "%~dp0scripts\healthcheck.py"
if %errorlevel% geq 2 (
    echo     [ERROR] Health check found hard failures. Fix above before starting.
    pause
    exit /b 1
)
echo.

:: -- Python backend -------------------------------------------
echo [2/2] Starting Python backend...
start "Bot Backend" /min cmd /c "cd /d %~dp0 && python interface/server.py & pause"

echo     Waiting for server to initialize...
timeout /t 4 /nobreak >nul

:: -- World Map ------------------------------------------------
echo [2.5/2] Launching world map...
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
echo   Bot is running.
echo   Backend: minimized window "Bot Backend"
echo   Avatar:  floating on your desktop
echo   Web UI:  http://localhost:5000
echo   Run stop-bot.bat to shut everything down.
echo ============================================================
echo.
pause
