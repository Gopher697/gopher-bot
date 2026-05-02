# gopher-workbench-mcp

A minimal local MCP server for giving AI coding assistants conservative access to
project SOPs, notes, git status/diff, and named preapproved commands.

## Safety Model

- No general shell execution tool is exposed.
- Projects are never discovered from the home directory.
- All project roots come from `config/projects.yaml`.
- All runnable commands come from `config/allowed_commands.yaml`, and each
  command must explicitly list the project names where it may run.
- Default behavior is read-only.
- The only write tool is `save_session_note(project, note)`, which appends a new
  timestamped Markdown file under the configured `session_notes_dir`.
- Path handling uses `pathlib.Path.resolve()` and rejects paths that escape the
  configured project root.
- Tool calls are logged to `logs/tool-calls.jsonl`.
- Session note bodies and note-search query text are not written to the log.

## MCP Resources

- `sop://ai-coding-loop`
- `sop://modding-workflow`
- `sop://troubleshooting`
- `sop://assistant-style`

Some MCP clients, including current Claude Desktop builds, may expose tools but
not resources in their chat UI. The bundled SOPs are therefore also available
through the read-only `list_sops()` and `read_sop(name)` tools. `read_sop` only
accepts bundled SOP names and does not accept paths.

## MCP Tools

- `list_sops()`
- `read_sop(name)`
- `list_projects()`
- `read_project_summary(project)`
- `search_project_notes(project, query)`
- `git_status(project)`
- `git_diff(project)`
- `run_allowed_command(project, command_name)`
- `save_session_note(project, note)`

## Setup

Install in editable mode from this folder:

```powershell
python -m pip install -e ".[dev]"
```

Run tests:

```powershell
python -m pytest
```

Run the server manually:

```powershell
python -m gopher_workbench_mcp.server
```

## Configure Projects

Edit `config/projects.yaml` and add only project folders you want the assistant
to access:

```yaml
projects:
  - name: my-project
    root: "D:/path/to/my-project"
    summary_file: "PROJECT.md"
    notes_dir: "notes"
    session_notes_dir: "notes/sessions"
```

## Configure Commands

Edit `config/allowed_commands.yaml` and add only commands you are comfortable
letting an assistant run by name. Commands are project-scoped: adding a project
to `config/projects.yaml` does not allow any command there unless that command's
`projects` list names the project.

```yaml
commands:
  - name: test
    description: "Run the project test suite."
    projects: ["my-project"]
    argv: ["python", "-m", "pytest"]
```

Commands run with `cwd` set to the selected project's configured root. If a
command omits `projects`, has an invalid project scope, or does not include the
selected project, the server refuses to run it.

## Example Codex MCP Config

Review and adapt this snippet for your Codex CLI/IDE MCP configuration. This
README does not edit your real `~/.codex/config.toml`.

```toml
[mcp_servers.gopher-workbench]
command = "python"
args = ["-m", "gopher_workbench_mcp.server"]
cwd = "D:/gopher-workbench-mcp"
```

If your Codex setup does not inherit the editable install environment, use an
absolute Python path or install the package into the same Python environment
Codex uses.

## Claude Setup Draft

For Claude Desktop on Windows, the likely config path is
`%APPDATA%\Claude\claude_desktop_config.json`. Review the existing config before
applying changes, and do not overwrite an existing Claude config without merging
the `mcpServers` entry.

```json
{
  "mcpServers": {
    "gopher-workbench": {
      "command": "python",
      "args": ["-m", "gopher_workbench_mcp.server"],
      "cwd": "D:/gopher-workbench-mcp"
    }
  }
}
```

If Claude cannot launch the server with `"python"`, replace
`"command": "python"` with the full path to the Python executable where
`gopher-workbench-mcp` is installed, for example:

```json
"command": "C:/Path/To/Python/python.exe"
```

If Claude cannot see the MCP server, first test from `D:\gopher-workbench-mcp`:

```powershell
python -m gopher_workbench_mcp.server
```

Restart Claude Desktop after changing its config. This gives Claude access to
the same MCP tools and configured projects as Codex.

If using Claude Code instead of Claude Desktop, configure the same MCP server
there using Claude Code's MCP setup method. Prefer local/project-scoped
configuration before global configuration when possible.

## Current Local Setup

This server is project-scoped through `D:\gopher-workbench-mcp\.codex\config.toml`.
Real project and command configs are local-only and ignored:

- `config/projects.yaml`
- `config/allowed_commands.yaml`

The tracked templates are:

- `config/projects.example.yaml`
- `config/allowed_commands.example.yaml`

Current private configured projects are:

- `gopher-workbench-mcp`
- `mcp-sandbox`
- `5d-chess-tools`

Commands are project-scoped. In the current private command config, `pytest` is
allowed for `gopher-workbench-mcp` and `5d-chess-tools`, `pytest-nongui` is
allowed only for `5d-chess-tools`, and `git-status` through
`run_allowed_command` is allowed only for `gopher-workbench-mcp`. Generated
`notes/sessions/*.md` files are ignored.

## Known Limitations

- `git_diff` can expose sensitive uncommitted changes and should be used
  deliberately.
- `5d-chess-tools` is not currently a Git repo, so dedicated `git_status` is
  skipped there.
- Full `pytest` for `5d-chess-tools` currently fails in this environment due to
  Tk/Tcl `init.tcl` issues.
- `pytest-nongui` is a temporary workaround until the 5D Chess test suite has
  proper GUI/Tk markers.

## Review Before Connecting

1. Confirm every root in `config/projects.yaml` is intentionally exposed.
2. Confirm every command in `config/allowed_commands.yaml` is safe for repeated
   assistant use in each project listed under that command.
3. Decide whether `git_diff` output may include sensitive local changes before
   enabling this server for broader assistants.
4. Inspect `logs/tool-calls.jsonl` periodically.
