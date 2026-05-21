# Antigravity Prompt: T69 + Neo4j JRE Fix

## Project context

You are working on **Gopher-bot** — a persistent neurosymbolic cognitive entity running on a local Windows PC.
The codebase is at `D:\Gopher Bot\gopher-bot\`.

Architecture snapshot:
- **Neo4j** graph database (local, port 7687) — the permanent memory substrate
- **Python backend** (`interface/server.py`) — Flask + SocketIO on port 5000
- **16 Python coordinators** in `coordinators/` — the cognitive pipeline
- **Godot avatar** — transparent borderless overlay window; connects to backend via `ws://localhost:5000/avatar-ws`
- **start-gopher-bot.bat** — launcher that starts Neo4j Desktop, polls port 7687, then starts backend + avatar

Commit all work. Never commit `world_models/config.py` (contains Neo4j credentials — it is gitignored). Always use single-line `-m '...'` commit messages. Run pytest with `--basetemp .tmp/pytest_T69` before committing.

---

## Task A: Fix Neo4j launcher (10 minutes)

**Problem:** `start-gopher-bot.bat` opens Neo4j Desktop but the database starts STOPPED — user must manually click Start each time. The `neo4j.bat start` command fails with "Unable to determine path to java.exe" because the bat file can't find the bundled JRE.

**What you know:**
- DBMS path: `C:\Users\gophe\.Neo4jDesktop2\Data\dbmss\dbms-54750ef6-52b6-4e69-b36e-2920fb10a8db\`
- The DBMS folder has no `jre\` subfolder — Neo4j Desktop 2 stores the JRE in its **Cache** folder
- Cache is at: `C:\Users\gophe\.Neo4jDesktop2\Cache\`
- System has no standalone Java installed (`java -version` fails)

**What to do:**
1. Search `C:\Users\gophe\.Neo4jDesktop2\Cache\` for `java.exe` — this is where the bundled JRE lives
2. Once you find the JRE path, update the `JAVA_EXE` and `JAVA_HOME` detection block in `start-gopher-bot.bat`
3. Call `neo4j.bat start` with JAVA_HOME set — this starts the DBMS as a background process (same as what Desktop's Start button does)
4. The existing 60-second polling loop for port 7687 handles the wait — no changes needed there
5. Neo4j Desktop still gets opened (it's useful for monitoring), but the DB starts automatically without user interaction

If no java.exe is found in Cache either, fall back to the current behavior (open Desktop, show NOTE to click Start) — do not break the existing fallback.

Commit: `'fix: auto-start Neo4j DBMS via bundled JRE in Desktop cache'`

---

## Task B: PySide6 World Map App — T69 scaffold (the main task)

### Vision

The **world map** is Gopher-bot's primary UI and its living environment. The computer IS its world. Open windows are rooms. Monitors are zones. The AI has geography — places it goes often, places it's never been.

This is not a dashboard. It is an infinite spatial canvas where Gopher-bot's attention and presence are *visible and real*.

### What to build

A PySide6 application (`interface/world_map.py`) with the following architecture:

#### 1. The canvas — `QGraphicsScene` / `QGraphicsView`

- **Infinite canvas** — the scene coordinate space is unlimited; the view pans and zooms
- **Monitor zones**: each physical monitor is rendered as a large labeled rectangle. Use `QApplication.screens()` to get real monitor geometry. Scale them down proportionally (e.g. 1 pixel per 4 screen pixels) so both monitors fit the canvas
- **Window rooms**: within each monitor zone, draw labeled rectangles for each open window. Use `pywinauto` + `win32gui` to enumerate open windows with their real positions and sizes. Filter out system windows (size < 100x100, invisible, taskbar, etc). Update the window list every 2 seconds
- **Avatar marker**: a small glowing dot (or triangle) on the canvas representing where Gopher-bot's attention currently is. Starts at center of primary monitor. Moves when Gopher-bot focuses a window
- Pan the view with middle-mouse drag or right-mouse drag. Zoom with scroll wheel

#### 2. Sidebar panels (docked, not on the canvas)

The canvas is Gopher-bot's *world*. Monitoring and control panels live in a separate `QDockWidget` sidebar so they don't clutter the spatial view:

- **State panel**: current coordinator state, neuromodulator levels (DA/NE/5HT/ACh), active goal. Read from a shared state dict updated by the backend
- **Audit panel**: last 20 lines of `logs/audit/turns.jsonl` auto-refreshed every 5 seconds
- The sidebar is collapsible. Default: open on the right side

#### 3. WebSocket connection to backend

Connect to `ws://localhost:5000/avatar-ws` (the same endpoint the Godot avatar uses). On each `/persona` message received:
```json
{
  "state": "working",
  "coordinator": "Reason",
  "focus_window": "gopher-bot - Visual Studio Code",
  "neuromodulators": {"da": 0.6, "ne": 0.4, "serotonin": 0.5, "ach": 0.7},
  "timestamp": "..."
}
```
- Update the avatar marker's position to the window matching `focus_window` (find it in the window room map)
- Update the state panel
- Animate the avatar marker moving to the new position (smooth, 300ms ease)

Use `websockets` or `websocket-client` for the WS connection. Run it in a background thread so the Qt event loop stays responsive.

#### 4. Window class design

```python
class WorldMapWindow(QMainWindow):
    def __init__(self):
        # Setup scene, view, sidebar panels
        # Start window enumeration timer (2s)
        # Start WS connection thread
    
    def refresh_windows(self):
        # pywinauto.Desktop(backend="uia").windows()
        # win32gui.GetWindowRect() for positions
        # Clear and redraw window rooms on scene
    
    def on_persona_update(self, payload: dict):
        # Move avatar marker
        # Update sidebar state
```

#### 5. App entry point

Add to `start-gopher-bot.bat` after the backend starts (before avatar):
```batch
echo [1.5/2] Launching world map...
start "" python "%~dp0interface\world_map.py"
timeout /t 2 /nobreak >nul
```

Also create `interface/world_map.py` with a `if __name__ == "__main__":` block that creates `QApplication` + `WorldMapWindow`.

### What NOT to build yet

- Do NOT render Gopher-bot's conversation history on the canvas (that comes later)
- Do NOT add drag-to-rearrange panels (that comes later)  
- Do NOT add 3D rendering
- Keep it readable and clean — this is a scaffold, not the final product

### Dependencies to add

Add to `pyproject.toml` optional extras or base requirements:
```
PySide6>=6.7
pywinauto>=0.6.8
pywin32>=306
websocket-client>=1.8
```

### Tests

Write `tests/test_world_map.py` with at minimum:
- Test that `WorldMapWindow` instantiates without error (headless — use `QApplication` with offscreen platform)
- Test that monitor zones are created (len > 0) from `QApplication.screens()`
- Test that persona payload parsing correctly extracts `state`, `coordinator`, `focus_window`

### Commit

`'T69: PySide6 world map app scaffold — monitor zones, window rooms, avatar marker, sidebar panels'`

---

## Constraints

- This is Windows-only code. `pywinauto` and `win32gui` are Windows APIs.
- The Godot avatar and the PySide6 world map are **separate processes** — both connect to the same `/avatar-ws` WebSocket and receive the same persona broadcasts. They don't talk to each other.
- Do not touch `interface/server.py` — the `/avatar-ws` endpoint already broadcasts persona state correctly.
- Do not touch any coordinator files.
- Never commit `world_models/config.py`.
