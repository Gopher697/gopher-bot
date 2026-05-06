# Starship Command Missing Bridges

This is a registry-first audit note for making Starship Command aware of the real
AI/workbench ecosystem. It is not a new log system, not a runtime integration,
and not persistent truth.

## Current Truth

- LM Studio is user-verified as already set up to host local models.
- Open WebUI is user-verified as already connected to LM Studio and able to use
  those models.
- Open WebUI remains manual availability only. The narrow
  `local_model_adapter.py` proof and GUI Server Doctor readiness check can call
  the configured local LM Studio endpoint when the server is running, but this is
  not MCP callability, an agent runtime, or autonomous specialist behavior.
- Process or app presence proves a tool exists for the user; it does not prove
  Starship can call it.
- ChatGPT Pro/Desktop and Claude Desktop are manual reasoning surfaces unless a
  verified callable route is added later.
- Codex is the primary implementation surface, but Starship does not yet launch,
  supervise, or message Codex as a crew resource.

## Top Missing Bridges

- Local models are exposed only through narrow Starship drydock diagnostics, not
  through Workbench MCP, specialists, or an agent runtime.
- Open WebUI is not callable through Starship or Workbench MCP.
- ChatGPT Pro/Desktop and Claude Desktop are manual-only reasoning surfaces.
- Codex is not yet represented as a Starship-callable Engineering resource.
- There is no crew communication protocol for model requests, outputs,
  escalations, specialist retirement, or command authorization.
- There is no job queue, worker lifecycle, or autonomous agent runtime.
- Archives has no connected retrieval pipeline for notes, corpora, manuals,
  source references, and current-state files.
- No model-role behavior and latency tests have been recorded.
- Open WebUI direct/external connections are a hazard unless kept to trusted
  local endpoints.

## MCP Integration Map

The current Workbench MCP server exposes conservative project access:

- SOP reads through `list_sops`, `read_sop`, and SOP resources.
- Project listing and summary reads through `list_projects` and
  `read_project_summary`.
- Project note/text search through `search_project_notes` and
  `search_project_text`.
- Git state through `git_status` and `git_diff`.
- Narrow command execution through `run_allowed_command`.
- Session-note creation through `save_session_note`.

It does not expose local model calls, Open WebUI calls, LM Studio calls, a job
queue, agent lifecycle management, or Starship crew messaging. The Starship
local model adapter and GUI Server Doctor are separate from Workbench MCP.

To let Starship request local-model assistance later, Workbench would need a
deliberate local-model bridge with trusted endpoint configuration, model allowlist,
request/response schema, timeouts, logging rules, and a no-autonomous-editing
boundary.

## Knowledge Layer Map

- `WORKBENCH_INDEX.md`, `PROJECT_REGISTRY.md`, `KNOWLEDGE_SPACES.md`, and
  `sops\` define Workbench orientation and authority.
- `config\projects.yaml` defines MCP operational project access.
- Project entrypoints define current authority only for their own project.
- GopherVault is broad external memory and reference unless a specific file is
  configured, promoted, or mirrored.
- Session notes, raw imports, staging folders, archives, pasted handoffs, and
  old agent outputs are historical/reference by default.
- Nomic embeddings are likely second-phase Archives infrastructure, not a first
  behavior test, because retrieval requires document-store and authority-filter
  plumbing first.

## Project Layer Map

| Project | Path | Entrypoint / Authority | Likely Division | Useful Surfaces | Hazards |
| --- | --- | --- | --- | --- | --- |
| `gopher-workbench-mcp` | `D:/gopher-workbench-mcp` | `README.md`, then `PROJECT.md`; `sops\` for Workbench SOP authority | Engineering, Archives, Command | Codex, Workbench MCP, local tests | README setup snapshot may be dated; avoid broad command exposure |
| `mcp-sandbox` | `D:/mcp-sandbox` | `PROJECT.md` | Engineering | Workbench MCP, local tests | Sandbox evidence is not real project truth |
| `5d-chess-tools` | `D:/5D Chess Tools` | `PROJECT.md`, then `README.md` | Science / Game Intelligence, Engineering | Codex, local tests, possible Qwen coder | GUI/Tk test caveats; verify current repo state |
| `gopher-vault` | `D:/GopherVault` | `PROJECT.md`, then relevant folder index | Archives | Manual chat surfaces, future retrieval | Broad vault notes are reference, not automatic authority |
| `worldbox-xianni` | `D:/Worldbox Xianni workspace` | `PROJECT.md`, then `notes/worldbox-xianni-sop.md` | Modding, Engineering, Tactical | Codex, Workbench MCP commands, local model review later | Do not confuse workspace, references, reports, backups, and live deployment |
| `cultivation-gsg` | `D:/Workflow/Cultivation Grand Strategy Game/Cultivation GSG` | Configured `PROJECT.md` is missing; use `README.md` with ambiguity flagged | Design, Engineering, Archives | Codex, local tests, wiki context | Code repo truth and wiki truth are split |
| `cultivation-gsg-wiki` | `D:/GopherVault/Projects/Cultivation GSG` | `00 START HERE.md` | Archives, Design | Manual reasoning, future retrieval | Raw archive imports are evidence, not canon |
| `invading-cultivation-army` | `C:/Users/gophe/AppData/Roaming/coe5/mods/Invading_Cultivation_Army` | `PROJECT_STATUS.md`, then `README.md` and current design docs | Modding, Engineering, Design | Codex, Workbench MCP, CoE5 skill | Live mod source of truth; archives are historical |
| `game-agent-core` | `D:/GameAgentCore` | `AGENTS.md`, then loop/autonomy/safety files | Science / Game Intelligence, Command | Manual planning models, future Starship routing | Architecture/doctrine only; no game-specific memory belongs here |
| `mi-chang-sheng-agent-workspace` | `D:/SteamLibrary/steamapps/common/觅长生/agent-workspace` | `SAFETY_RULES.md`, then current session/goals/world state | Science / Game Intelligence | Manual game-agent analysis, future visual/local models | Do not modify game install outside `agent-workspace` |
| `dwarf-fortress-agent-workspace` | `D:/SteamLibrary/steamapps/common/Dwarf Fortress/agent-workspace` | `SAFETY_RULES.md`, then current session/goals/world state | Science / Game Intelligence | Manual game-agent analysis, future visual/local models | Do not modify game install outside `agent-workspace` |

## First Integration Tests

### A. Zero-Code Open WebUI -> LM Studio Check

This bridge is already user-verified. The next useful step is not configuration;
it is recording the working manual facts if the user chooses:

- Confirm from Open WebUI that a local LM Studio-hosted model answers a simple
  prompt.
- Record the local endpoint and model name as manual availability.
- Keep the connection limited to trusted local endpoints.
- Do not scan ports, inspect running processes, modify app settings, or add
  Starship GUI, MCP, or agent-runtime code.

### B. Qwen2.5-Coder-14B Engineering Behavior Test

Use `qwen2.5-coder-14b-instruct` as the first Engineering local-model behavior
test target through `local_model_adapter.py` when LM Studio is running:

- Send the fixed Starship Command routing/unit-test prompt.
- Do not let the model edit files directly.
- Record response latency, usefulness, correctness, and whether the answer is
  concise enough for real working sessions.
- First manual run succeeded through LM Studio in 20.199s, but the response was
  coherent and shallow and misunderstood the routing-test prompt as a
  game/gameplay scenario.
- The screenshot-observed 2048 context window is a likely quality limitation;
  retest at 8192 or higher if hardware allows before assigning Engineering
  deep-consult status.
- If latency is unacceptable, test `qwen2.5-3b-instruct` as a faster temporary
  Engineering triage target despite lower expected capability.
- Do not use Coder-14B for routine First Officer chatter until latency and
  usefulness are verified.
- Do not build Starship infrastructure around Coder-14B until speed and
  usefulness are verified.

## Manual-Only vs Starship-Callable

Manual-only today:

- ChatGPT Pro
- ChatGPT Desktop app
- Claude Desktop / local Claude surface
- Open WebUI
- VS Code / Continue until verified
- Local model roles listed in `command_registry.yaml` except the narrow LM
  Studio adapter path.

Partially callable or callable outside Starship:

- Codex is usable as the primary implementation surface, but not as a
  Starship-callable crew resource.
- GitHub connector/access may be available in Codex context, but Starship has no
  direct connector bridge.
- Workbench MCP is callable by configured MCP clients, but Starship Command has
  no direct MCP client bridge yet.
- Local scripts and tests are callable through the current shell or narrow MCP
  allowlists, not through Starship crew routing.
- LM Studio is partially callable through `local_model_adapter.py` only when the
  local server is running and the configured model is available.
- Starship GUI can run the Server Doctor readiness check from the local machine
  when LM Studio is available.

Starship-callable today:

- Starship CLI/core/GUI rule-based routing and templates.
- The narrow `local_model_adapter.py` Engineering behavior test and GUI Server
  Doctor readiness check; no MCP, autonomous, or specialist-runtime integration.
