# Codex Task — Wire Discord bridge into start-bot.bat and stop-bot.bat

## Background

`interface/discord_bot.py` is the Discord bridge for Gopher-bot. It was
implemented and committed (b2b683f) but never wired into the startup scripts.
The bridge works correctly when launched manually via:

```
python interface/discord_bot.py
```

It reads `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL` from `world_models/config.py`.
If `DISCORD_BOT_TOKEN` is empty or missing, `main()` prints an error and exits
with code 1 — cleanly, no crash.

## Task

Make two surgical changes — one to `start-bot.bat`, one to `stop-bot.bat`.
Do NOT touch any Python files.

---

## Change 1 — start-bot.bat

Add a Discord bridge launch block **after** the `[2/2] Starting Python backend...`
section and its 4-second wait, and **before** the `[2.5/2] Launching world map...`
section.

The block should:
1. Check whether `DISCORD_BOT_TOKEN` is configured by running a Python one-liner
   that exits 0 if the token is set and non-empty, 1 otherwise.
2. If token is set: launch `interface/discord_bot.py` in a new minimized window
   titled `"Discord Bridge"`, following the same pattern as the Bot Backend launch.
3. If token is not set: print a skip message and continue.

Insert this block at line ~100 (after `timeout /t 4 /nobreak >nul`):

```batch
:: -- Discord bridge -------------------------------------------
python -c "from world_models import config; exit(0 if getattr(config, 'DISCORD_BOT_TOKEN', '').strip() else 1)" >nul 2>&1
if %errorlevel%==0 (
    echo [2/2] Starting Discord bridge...
    start "Discord Bridge" /min cmd /c "cd /d "%~dp0" && python interface/discord_bot.py & pause"
    echo     Discord bridge launched.
) else (
    echo [2/2] Discord bridge skipped ^(DISCORD_BOT_TOKEN not set^).
)
echo.
```

Also update the "Bot is running." summary block at the bottom to mention the
Discord bridge when it starts. Add one line after the `Backend:` and `Avatar:` lines:

```
echo   Discord: running in minimized window "Discord Bridge" ^(if token configured^)
```

---

## Change 2 — stop-bot.bat

Add a line to kill the Discord bridge window, following the same pattern as the
existing `taskkill` calls. Insert after the `Stopping Python backend...` block:

```batch
echo Stopping Discord bridge...
taskkill /FI "WINDOWTITLE eq Discord Bridge" /T /F >nul 2>&1
```

---

## What NOT to change

- Do not modify any Python files.
- Do not change the Neo4j, world map, or avatar launch blocks.
- Do not change the health check or migration blocks.
- Do not alter any existing `taskkill` lines in stop-bot.bat.

---

## Verification

1. Run `start-bot.bat` with `DISCORD_BOT_TOKEN` set in `world_models/config.py`.
   Confirm a minimized window titled `"Discord Bridge"` appears and that
   Gopher-bot comes online in Discord.

2. Run `start-bot.bat` with `DISCORD_BOT_TOKEN` absent or empty.
   Confirm the skip message prints and no Discord window opens.

3. Run `stop-bot.bat`. Confirm the Discord bridge window closes alongside the
   other processes.

---

## Security invariant

Run `git status` before committing. If `world_models/config.py` appears, STOP.

## Commit

```
git commit -m "feat: wire Discord bridge into start-bot.bat / stop-bot.bat"
```
