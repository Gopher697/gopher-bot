# Codex Prompt: Build Standalone gopher-workbench MCP Server

## Context

We are separating two things that currently live in the same folder:
1. The **Gopher-bot AI brain** (coordinators, interface, governance docs) — this stays and the current folder will be renamed to `D:\gopher-bot\`
2. The **workbench MCP server** — the tool infrastructure that connects Claude to projects via MCP

Your job is to build the new standalone workbench MCP server at `D:\gopher-workbench\`.
The current MCP server source lives at `D:\gopher-workbench-mcp\src\gopher_workbench_mcp\`.
You will copy and adapt it — not rewrite it from scratch.

Do NOT modify anything in `D:\gopher-workbench-mcp\`. Build only in `D:\gopher-workbench\`.

---

## Step 1: Create the directory structure

Create these directories:

```
D:\gopher-workbench\
D:\gopher-workbench\src\
D:\gopher-workbench\src\gopher_workbench\
D:\gopher-workbench\config\
D:\gopher-workbench\sops\
D:\gopher-workbench\logs\
D:\gopher-workbench\notes\
D:\gopher-workbench\notes\sessions\
```

---

## Step 2: Copy and adapt the Python source

Copy these three files verbatim — do not change their content:

- `D:\gopher-workbench-mcp\src\gopher_workbench_mcp\config.py`
  → `D:\gopher-workbench\src\gopher_workbench\config.py`

- `D:\gopher-workbench-mcp\src\gopher_workbench_mcp\workbench.py`
  → `D:\gopher-workbench\src\gopher_workbench\workbench.py`

Then copy `server.py` with these specific changes:

- Source: `D:\gopher-workbench-mcp\src\gopher_workbench_mcp\server.py`
- Destination: `D:\gopher-workbench\src\gopher_workbench\server.py`

Changes to make in the copied `server.py`:
1. Change the import line `from .workbench import Workbench, WorkbenchError, validate_startup_config` — leave it identical (it still works).
2. Change `ROOT = Path(__file__).resolve().parents[2]` — leave identical.
3. Change `mcp = FastMCP("gopher-workbench-mcp")` → `mcp = FastMCP("gopher-workbench")`
4. Change the entry point function name `main` — leave identical.
5. At the bottom, change the argparse description from `"Run the gopher workbench MCP server."` → `"Run the standalone gopher-workbench MCP server."`

Create `D:\gopher-workbench\src\gopher_workbench\__init__.py` as an empty file.

---

## Step 3: Create pyproject.toml

Create `D:\gopher-workbench\pyproject.toml` with this exact content:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "gopher-workbench"
version = "0.1.0"
description = "Standalone workbench MCP server — project SOPs, notes, git state, and allowlisted commands."
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
  "mcp>=1.0.0",
  "PyYAML>=6.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
]

[project.scripts]
gopher-workbench = "gopher_workbench.server:main"

[tool.hatch.build.targets.wheel]
packages = ["src/gopher_workbench"]
```

---

## Step 4: Create config files

Create `D:\gopher-workbench\config\projects.yaml` with this exact content:

```yaml
# Projects are never auto-discovered. Add only folders you want assistants to see.
projects:
  - name: gopher-bot
    root: "D:/gopher-bot"
    summary_file: "PROJECT.md"
    notes_dir: "notes"
    session_notes_dir: "notes/sessions"
  - name: mcp-sandbox
    root: "D:/mcp-sandbox"
    summary_file: "PROJECT.md"
    notes_dir: "notes"
    session_notes_dir: "notes/sessions"
  - name: 5d-chess-tools
    root: "D:/5D Chess Tools"
    summary_file: "PROJECT.md"
    notes_dir: "notes"
    session_notes_dir: "notes/sessions"
  - name: gopher-vault
    root: "D:/GopherVault"
    summary_file: "PROJECT.md"
    notes_dir: "notes"
    session_notes_dir: "notes/sessions"
  - name: worldbox-xianni
    root: "D:/Worldbox Xianni workspace"
    summary_file: "PROJECT.md"
    notes_dir: "notes"
    session_notes_dir: "notes/sessions"
  - name: worldbox-xianni-repo
    root: "D:/Worldbox Xianni workspace/repo_github"
    summary_file: "README.md"
    notes_dir: "docs"
    session_notes_dir: "reports"
  # Cultivation GSG code repo. For major design/implementation work, also
  # consult cultivation-gsg-wiki and read "00 START HERE.md" first.
  - name: cultivation-gsg
    root: "D:/Workflow/Cultivation Grand Strategy Game/Cultivation GSG"
    summary_file: "PROJECT.md"
    notes_dir: "notes"
    session_notes_dir: "notes/sessions"
  # Cultivation GSG project-memory / Obsidian wiki repo.
  - name: cultivation-gsg-wiki
    root: "D:/GopherVault/Projects/Cultivation GSG"
    summary_file: "00 START HERE.md"
    notes_dir: "."
    session_notes_dir: "notes/sessions"
  - name: invading-cultivation-army
    root: "C:/Users/gophe/AppData/Roaming/coe5/mods/Invading_Cultivation_Army"
    summary_file: "PROJECT_STATUS.md"
    notes_dir: "docs/notes"
    session_notes_dir: "docs/notes/sessions"
  - name: game-agent-core
    root: "D:/GameAgentCore"
    summary_file: "AGENTS.md"
    notes_dir: "notes"
    session_notes_dir: "notes/sessions"
  - name: worldbox-agent-workspace
    root: "D:/SteamLibrary/steamapps/common/worldbox/agent-workspace"
    summary_file: "CURRENT_SESSION.md"
    notes_dir: "."
    session_notes_dir: "notes/sessions"
  - name: mi-chang-sheng-agent-workspace
    root: "D:/SteamLibrary/steamapps/common/觅长生/agent-workspace"
    summary_file: "CURRENT_SESSION.md"
    notes_dir: "."
    session_notes_dir: "notes/sessions"
  - name: dwarf-fortress-agent-workspace
    root: "D:/SteamLibrary/steamapps/common/Dwarf Fortress/agent-workspace"
    summary_file: "CURRENT_SESSION.md"
    notes_dir: "."
    session_notes_dir: "notes/sessions"
  - name: 5d-chess-with-multiverse-time-travel-agent-workspace
    root: "D:/SteamLibrary/steamapps/common/5dchesswithmultiversetimetravel/agent-workspace"
    summary_file: "CURRENT_SESSION.md"
    notes_dir: "."
    session_notes_dir: "notes/sessions"
  - name: distant-worlds-universe-agent-workspace
    root: "D:/SteamLibrary/steamapps/common/Distant Worlds Universe/agent-workspace"
    summary_file: "CURRENT_SESSION.md"
    notes_dir: "."
    session_notes_dir: "notes/sessions"
  - name: factorio-agent-workspace
    root: "D:/SteamLibrary/steamapps/common/Factorio/agent-workspace"
    summary_file: "CURRENT_SESSION.md"
    notes_dir: "."
    session_notes_dir: "notes/sessions"
  - name: elemental-reforged-agent-workspace
    root: "D:/SteamLibrary/steamapps/common/Elemental Reforged/agent-workspace"
    summary_file: "CURRENT_SESSION.md"
    notes_dir: "."
    session_notes_dir: "notes/sessions"
  - name: warsim-the-realm-of-aslona-agent-workspace
    root: "D:/SteamLibrary/steamapps/common/Warsim The Realm of Aslona/agent-workspace"
    summary_file: "CURRENT_SESSION.md"
    notes_dir: "."
    session_notes_dir: "notes/sessions"
  - name: amazing-cultivation-simulator-agent-workspace
    root: "D:/SteamLibrary/steamapps/common/AmazingCultivationSimulator/agent-workspace"
    summary_file: "CURRENT_SESSION.md"
    notes_dir: "."
    session_notes_dir: "notes/sessions"
```

Create `D:\gopher-workbench\config\allowed_commands.yaml` with this exact content:

```yaml
# Commands are invoked by name only. There is no arbitrary shell tool.
commands:
  - name: pytest
    description: "Run the Python test suite for this project."
    projects: ["gopher-bot", "5d-chess-tools"]
    argv: ["python", "-m", "pytest"]
  - name: run-tests
    description: "Run the canonical Windows test runner for 5D Chess Tools."
    projects: ["5d-chess-tools"]
    argv: ["cmd", "/c", "run_tests.bat"]
  - name: git-status
    description: "Show short git status. Prefer the dedicated git_status tool."
    projects: ["gopher-bot"]
    argv: ["git", "status", "--short"]
  - name: pytest-nongui
    description: "Run the 5D Chess Tools non-GUI test suite without Tk-backed tests."
    projects: ["5d-chess-tools"]
    argv:
      - "python"
      - "-m"
      - "pytest"
      - "-p"
      - "no:cacheprovider"
      - "-k"
      - "not LauncherNavigationUiTests and not LauncherThreatComposerUiTests and not BoardBrowserUiTests and not MoveValidationWarningsTests and not test_replay_navigation_behavior and not test_history_selection_drives_replay_state and not test_study_mode_state_is_separate_from_live_authoring and not test_safe_return_from_study_mode_to_live_authoring"
  - name: xianni-build
    description: "Build the WorldBox XianNi mod into repo_github/build_staging. Does not deploy."
    projects: ["worldbox-xianni"]
    argv: ["dotnet", "build", "D:/Worldbox Xianni workspace/repo_github/XianniMod.csproj", "-c", "Release"]
  - name: xianni-git-status
    description: "Show short git status for the WorldBox XianNi repo."
    projects: ["worldbox-xianni"]
    argv: ["git", "-C", "D:/Worldbox Xianni workspace/repo_github", "status", "--short"]
  - name: xianni-git-diff
    description: "Show full git diff for the WorldBox XianNi repo."
    projects: ["worldbox-xianni"]
    argv: ["git", "-C", "D:/Worldbox Xianni workspace/repo_github", "diff", "--"]
  - name: xianni-scan-code-chinese
    description: "Read-only scan for Chinese characters in XianNi C# source."
    projects: ["worldbox-xianni"]
    argv: ["rg", "-n", "[\\p{Han}]", "D:/Worldbox Xianni workspace/repo_github/code", "-g", "*.cs"]
  - name: xianni-search-player-log
    description: "Read-only search of the WorldBox Player.log for Xianni/NML runtime errors."
    projects: ["worldbox-xianni"]
    argv: ["powershell", "-NoProfile", "-Command", "Select-String -LiteralPath 'C:\\Users\\gophe\\AppData\\LocalLow\\mkarpenko\\WorldBox\\Player.log' -Pattern 'XIAN_NI_MOD|Xianni|XianNi|XianniMod|disabled due to an error|Field|Method|inaccessible|TypeLoadException|ReflectionTypeLoadException|FileNotFoundException|MethodAccessException|MissingMethodException|NullReferenceException|IL Compile Error|Exception' -Context 4,8"]
  - name: xianni-search-bepinex-log
    description: "Read-only search of the WorldBox BepInEx log for Xianni/NML runtime errors."
    projects: ["worldbox-xianni"]
    argv: ["powershell", "-NoProfile", "-Command", "Select-String -LiteralPath 'D:\\SteamLibrary\\steamapps\\common\\worldbox\\BepInEx\\LogOutput.log' -Pattern 'XIAN_NI_MOD|Xianni|XianNi|XianniMod|disabled due to an error|Field|Method|inaccessible|TypeLoadException|ReflectionTypeLoadException|FileNotFoundException|MethodAccessException|MissingMethodException|NullReferenceException|IL Compile Error|Exception' -Context 4,8"]
```

---

## Step 5: Copy SOPs

Copy these files verbatim:

- `D:\gopher-workbench-mcp\sops\ai-coding-loop.md` → `D:\gopher-workbench\sops\ai-coding-loop.md`
- `D:\gopher-workbench-mcp\sops\modding-workflow.md` → `D:\gopher-workbench\sops\modding-workflow.md`
- `D:\gopher-workbench-mcp\sops\troubleshooting.md` → `D:\gopher-workbench\sops\troubleshooting.md`
- `D:\gopher-workbench-mcp\sops\assistant-style.md` → `D:\gopher-workbench\sops\assistant-style.md`
- `D:\gopher-workbench-mcp\sops\workbench-orientation.md` → `D:\gopher-workbench\sops\workbench-orientation.md`

---

## Step 6: Create README.md

Create `D:\gopher-workbench\README.md`:

```markdown
# gopher-workbench MCP server

Standalone workbench MCP server providing Claude with access to project files,
SOPs, session notes, git status, and allowlisted commands.

Separated from the gopher-bot AI brain repo on 2026-05-20.

## Installation

```
cd D:\gopher-workbench
pip install -e . --break-system-packages
```

## Claude Desktop connection

In claude_desktop_config.json, replace the old gopher-workbench-mcp entry with:

```json
"gopher-workbench": {
  "command": "python",
  "args": ["-m", "gopher_workbench.server"],
  "cwd": "D:\\gopher-workbench"
}
```

Or using the installed script:

```json
"gopher-workbench": {
  "command": "gopher-workbench"
}
```

## Configuration

- `config/projects.yaml` — allowlisted project roots
- `config/allowed_commands.yaml` — allowlisted commands per project
- `sops/` — standard operating procedures exposed as MCP resources
```

---

## Step 7: Install the package

Run from `D:\gopher-workbench\`:

```
pip install -e . --break-system-packages
```

Verify it installed cleanly. If there are import errors, check that the `src/gopher_workbench/` package files were copied correctly and that all three files (`__init__.py`, `config.py`, `workbench.py`, `server.py`) are present.

---

## Step 8: Verify

Run this quick smoke test from `D:\gopher-workbench\`:

```
python -c "from gopher_workbench.server import create_server; print('OK')"
```

It should print `OK`. If it throws an import error or config error, fix the issue before stopping.

---

## What NOT to do

- Do NOT touch anything in `D:\gopher-workbench-mcp\`
- Do NOT initialize a git repo in `D:\gopher-workbench\` — it does not need one
- Do NOT copy `world_models/`, `coordinators/`, `interface/`, or any bot source code
- Do NOT copy `.git/`, `tests/`, or `logs/` from the old location
