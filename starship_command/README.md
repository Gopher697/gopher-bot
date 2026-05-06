# Starship Command Operations V1

Starship Command Operations is a local, rule-based command-management console
for routing missions across visible bridge divisions, preparing specialist
briefs, generating template-based Codex mission orders, and producing compact
bridge log / handoff text.

The visual browser GUI is the intended primary user-facing interface. The CLI
remains useful as a backend/test harness for the same core routing and template
logic.

Starship Command Operations is not a terminal-first system, corporate dashboard,
generic office org chart, physical bridge floorplan, MCP server, API client,
autonomous agent runtime, commit tool, or replacement for repo-specific startup
rules.

Current phase: drydock prototype. The operating principle is that the Captain
gives intent; Engineering, Codex, and Starship run diagnostics and report back.
The ship is not commissioned until the First Officer can receive an order, route
it to a crew member who produces a useful artifact, and complete the full loop
without the user touching a terminal.

## Command Doctrine

"Codex and Starship Command are Engineering. The Captain approves, judges, and
authorizes. Codex inspects, implements, tests, and reports. The user is never
the integration layer."

Terminal commands are Engineering actions, not normal Captain workflow. The GUI
is the primary interface for routine checks. Starship may inspect and test local
resources directly when safe, but runtime-changing operations require explicit
Captain authorization and a verified local control path.

## Command Operations GUI

Launch from the Workbench root:

```powershell
python starship_command\command_operations_gui.py
```

The launcher prints the local URL and opens the browser by default. To launch
without opening a browser:

```powershell
python starship_command\command_operations_gui.py --no-open
```

The GUI runs on Python's standard library `http.server` stack. It makes no
external API calls and adds no external dependencies. The local model readiness
and Model Operations checks can call the configured localhost LM Studio endpoint
when the GUI is running on the user's machine.

## Divisions

- Command Division: First Officer routing, prioritization, mission breakdown,
  cross-division assignment, and specialist deployment.
- Engineering Division: implementation, debugging, code, tests, scripts, repos,
  builds, CLI/backend work, and Codex execution.
- Computer Core / Archives: continuity, project memory, notes, corpus
  organization, reference systems, authority maps, stale context, and handoffs.
- Tactical / Safety: explicit risk and safety reviews, plus supporting review
  for destructive, broad, live-runtime, cross-project, or unclear-authority
  hazards.
- Science / Game Intelligence: game-analysis assistants, game workspaces,
  save-state tracking, gameplay decision support, strategy analysis, simulation
  analysis, and adaptive game-agent systems.
- Modding Division: mod design/triage, game mod constraints, translation
  workflows, loader/runtime concerns, version separation, mod-specific
  diagnosis, and game-specific data/config issues.
- Design Bureau: speculative game design, roadmap critique, faction/system
  design, design synthesis, design-lane boundaries, source-corpus-driven design
  interpretation, and project direction.

## V1 Limitations

The GUI is visual and interactive, but officer behavior remains rule/template
based. It does not launch autonomous agents or call an LLM/API. Deploying a
specialist creates a tracked specialist brief and session-state record, not a
running process.

Session state is in memory only for v1. It resets at GUI launch and is not
persistent truth. No `command_state.yaml` is created by default, and bridge
logs / handoffs are displayed for copying rather than saved automatically.

## CLI Harness

Run from the Workbench root:

```powershell
python starship_command\starship_console.py list-stations
python starship_command\starship_console.py route "debug the nostdrec recruit screen issue in the CoE5 mod"
python starship_command\starship_console.py spawn-specialist "turn Er Gen corpus notes into a usable Codex reference system"
python starship_command\starship_console.py codex-prompt "add focused tests for a repo change"
python starship_command\starship_console.py handoff
```

## Local Model Bridge Proof

`local_model_adapter.py` is a narrow manual proof for calling a local LM Studio
OpenAI-compatible endpoint. It is not an agent runtime, does not edit files,
does not call external APIs, and is not wired into autonomous specialist
behavior.

The default non-secret local endpoint and model live in
`command_registry.yaml`:

```text
http://localhost:1234/v1
qwen2.5-coder-14b-instruct
```

Do not store API keys, tokens, external endpoints, or non-local credentials in
`command_registry.yaml`. If future work needs secrets, put them in a gitignored
local config file instead.

When LM Studio's local server is running, use:

```powershell
python starship_command\local_model_adapter.py config
python starship_command\local_model_adapter.py list-models
python starship_command\local_model_adapter.py test-engineering
```

The Engineering test sends one fixed prompt, measures latency, and prints the
response for human judgment. It does not score quality automatically.

## Model Operations

Model Operations is the unified GUI workflow for local model status, readiness,
and authorized reload/retest work. The user should not need to use terminal
commands for normal model checks.

The panel can check local model status, list models visible through the
configured endpoint, show live context windows when available, fall back to
registry-observed context values, run readiness tests, prepare the Coder-14B
higher-context retest, and request an authorized Coder-14B reload at `4096` or
`8192` context when a safe local LM Studio control path is available.

Any runtime-changing model action requires Captain authorization in the GUI. A
passive status or readiness check never loads, unloads, or reloads models. A
reload request explains the affected model, target context, expected risk, and
that LM Studio runtime state may change.

The lower-level `local_model_server_doctor.py` module remains a backend/debug
harness for Codex and advanced troubleshooting, but Model Operations is the
user-facing workflow. The check runs from the local GUI server process, so it can reach
`http://localhost:1234/v1` only when Starship Command is running on the user's
machine with LM Studio available locally.

Terminal commands remain backend/debug options for Codex or advanced
troubleshooting:

```powershell
python -B starship_command\local_model_server_doctor.py check
python -B starship_command\local_model_server_doctor.py list-models
python -B starship_command\local_model_server_doctor.py readiness
```

The backend diagnostic checks the configured localhost endpoint, lists visible
model ids, compares them with registry/user-observed model ids, runs lightweight
readiness prompts for available text models, measures latency, and prints a
plain readiness report. Model Operations reuses those helpers. It does not
modify Open WebUI settings, project files, commits, or agent runtime state.

The user should not need to manually understand server internals. Starship can
only call models exposed through the configured local endpoint. Starship may
inspect and test local models; it may only change LM Studio runtime state after
Captain authorization and only through a verified local control path.

Context window size matters. A low context setting such as `2048` can reduce
quality for code and project reasoning, especially when a prompt depends on
repo-specific terms. The Server Doctor reports `context_window` when the local
endpoint exposes it; otherwise it prints `context_window: unknown` and asks the
user to verify the setting in LM Studio before comparing model quality.

Current Coder-14B status: the LM Studio bridge call succeeded manually with
`qwen2.5-coder-14b-instruct`, but latency was `20.199s`, the observed LM Studio
context was `2048`, and the response was coherent but weak because it
misunderstood a Starship routing-test prompt as a game/gameplay scenario. Treat
Coder-14B as callable but pending usefulness retest at a higher context window,
starting with `4096`, then `8192` if practical. Do not assign it as a trusted
Engineering deep-consult resource or use it for routine First Officer chatter
until latency and usefulness are verified. If higher context is too slow,
classify it as deep consult only or test `qwen2.5-3b-instruct` as a faster
temporary Engineering triage model.

## Manual GUI Smoke Tests

- Route `debug the nostdrec recruit screen issue in the CoE5 mod`; expected:
  Engineering Division primary, Modding Division supporting, Tactical / Safety
  absent.
- Deploy a specialist for `turn Er Gen corpus notes into a usable Codex reference
  system`; expected: specialist appears under Computer Core / Archives and says
  no autonomous agent was launched.
- Generate a Codex mission order; expected: output clearly says it is
  template-based and non-LLM-generated.
- Create a bridge log / handoff; expected: compact Markdown appears in the
  output panel and is not saved automatically.
- Use Copy Output; expected: current output panel text is copied to clipboard.
- Use Model Operations; expected: local status/readiness appears in the output
  panel, runtime-changing reload actions require Captain authorization, and no
  autonomous model work is launched.

## Evolution Ladder

```text
static notes
-> CLI/core routing proof
-> visual Command Operations GUI
-> visible divisions and duty roster
-> specialist deployment tracking
-> template-based Codex mission orders
-> bridge-log handoff loop
-> model operations and authorized local-model retesting
-> tool integrations
-> persistent agent environment
-> animated/Agent-Craft-like workspace
```
