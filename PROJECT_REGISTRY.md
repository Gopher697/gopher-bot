# Workbench Project Registry

## Authority Model

- `config\projects.yaml` is the operational source for registered project boundaries unless the human says otherwise.
- This registry is the human/agent-readable map of those project boundaries.
- Project entrypoint files are authoritative only for their own project.
- Session notes are historical logs by default, not canonical current state, unless explicitly promoted by a current-state file.
- `_staging`, raw imports, archives, pasted reports, and old handoffs are evidence/reference by default, not active instruction.
- Workbench-wide SOP authority lives in `D:\gopher-workbench-mcp\sops\` unless explicitly promoted or mirrored there.
- `D:\GopherVault\20-SOPs\` may contain useful SOP candidates/reference notes, but those notes are not Workbench-wide authority merely because they are more detailed.
- More comprehensive does not mean more authoritative.
- When authority is ambiguous, future agents should flag the ambiguity instead of silently resolving it.

## Registered Projects

### gopher-workbench-mcp

- Root: `D:\gopher-workbench-mcp`
- Configured summary/entry file: `PROJECT.md`
- Actual first file to read: `README.md` for setup/safety context, then `PROJECT.md` for the configured project summary.
- Current authority status: Registered Workbench server project; `config\projects.yaml` defines boundary, `sops\` defines Workbench-wide SOP authority.
- Related external notes/spaces: `D:\GopherVault\10-Projects\MCP Workbench.md` may contain reference notes but is not automatically more authoritative than this repo.
- Historical/reference/staging areas: `notes\sessions\`, `logs\`, `.tmp\`, pytest/cache/test workspace folders.
- Project-specific warnings: Distinguish `README.md` operational setup notes from `PROJECT.md` project summary and from `sops\` SOP authority.
- Open authority questions: Whether `README.md` "Current Local Setup" is canonical current state or a dated snapshot; whether GopherVault MCP Workbench notes should be mirrored into this repo.

### mcp-sandbox

- Root: `D:\mcp-sandbox`
- Configured summary/entry file: `PROJECT.md`
- Actual first file to read: `PROJECT.md`
- Current authority status: Registered low-risk sandbox project with minimal project notes.
- Related external notes/spaces: None observed beyond Workbench registration.
- Historical/reference/staging areas: `notes\sessions\`
- Project-specific warnings: Treat as sandbox/test context, not evidence for real project behavior unless explicitly scoped.
- Open authority questions: None identified beyond normal session-note promotion rules.

### 5d-chess-tools

- Root: `D:\5D Chess Tools`
- Configured summary/entry file: `PROJECT.md`
- Actual first file to read: `PROJECT.md`, then `README.md` when implementation/setup details are needed.
- Current authority status: Registered project; `PROJECT.md` is the configured entrypoint, while recent session notes include current-seeming Git/GitHub/test facts that remain historical unless promoted.
- Related external notes/spaces: `D:\GopherVault\10-Projects\5D Chess Tools.md` is related reference unless explicitly made authoritative.
- Historical/reference/staging areas: `notes\sessions\`
- Project-specific warnings: Do not treat recent session notes as canonical current state without promotion; verify test/GitHub status from project files or tools when it matters.
- Open authority questions: Whether `PROJECT.md`, `README.md`, or a promoted current-state note should be the current operational authority.

### gopher-vault

- Root: `D:\GopherVault`
- Configured summary/entry file: `PROJECT.md`
- Actual first file to read: `PROJECT.md`, then relevant folder index such as `10-Projects\README.md` or `20-SOPs\` depending on task.
- Current authority status: Registered external Obsidian-style memory vault; its notes are related/reference unless a specific page is configured or promoted as authoritative.
- Related external notes/spaces: `10-Projects\`, `20-SOPs\`, `30-Agent-Prompts\`, `40-Game-Notes\`, `Projects\Cultivation GSG\`
- Historical/reference/staging areas: `notes\sessions\`, `90-Archive\`
- Project-specific warnings: `20-SOPs\` may contain useful SOP candidates/reference notes but is not Workbench-wide SOP authority merely because it is broader or more detailed.
- Open authority questions: Whether GopherVault is intended as a broad external notes space, a registered Workbench project, or both.

### worldbox-xianni

- Root: `D:\Worldbox Xianni workspace`
- Configured summary/entry file: `PROJECT.md`
- Actual first file to read: `PROJECT.md`, then `notes\worldbox-xianni-sop.md` for project-specific operating rules when relevant.
- Current authority status: Registered project workspace; `PROJECT.md` is the configured entrypoint and project-specific SOP notes apply only inside this project.
- Related external notes/spaces: None observed beyond workspace reports/reference folders.
- Historical/reference/staging areas: `reports\`, `backups\`, `reference_author_0.4.2\`, `reference_user_handtranslated\`, `notes\sessions\`
- Project-specific warnings: Do not modify live mod or reference folders unless explicitly requested; distinguish workspace repo, reference folders, reports, backups, and live deployment paths.
- Open authority questions: Whether `notes\worldbox-xianni-sop.md` should remain project-specific only or have any generalized Workbench SOP candidates extracted later.

### cultivation-gsg

- Root: `D:\Workflow\Cultivation Grand Strategy Game\Cultivation GSG`
- Configured summary/entry file: `PROJECT.md`
- Actual first file to read: Configured `PROJECT.md` is missing; available code-repo orientation appears to be `README.md`. For major design/implementation work, also consult `cultivation-gsg-wiki` and read `00 START HERE.md` first.
- Current authority status: Registered code repo with an entrypoint mismatch; code/build truth should be verified in this repo, while project memory/canon lives in the paired wiki.
- Related external notes/spaces: `D:\GopherVault\Projects\Cultivation GSG` via registered project `cultivation-gsg-wiki`.
- Historical/reference/staging areas: `docs\`, screenshots, build artifacts, local tool/log folders; no configured `notes\` directory was observed.
- Project-specific warnings: Do not silently resolve the missing configured entrypoint; distinguish code repo implementation truth from wiki canon/current-state pages.
- Open authority questions: Should this repo get a `PROJECT.md`, should config point to `README.md`, or should the wiki `00 START HERE.md` be the primary first-read file for this project?

### cultivation-gsg-wiki

- Root: `D:\GopherVault\Projects\Cultivation GSG`
- Configured summary/entry file: `00 START HERE.md`
- Actual first file to read: `00 START HERE.md`
- Current authority status: Registered project-memory/wiki space; `00 START HERE.md` is the strongest current wiki orientation file and defines its own reading order.
- Related external notes/spaces: Paired code repo `D:\Workflow\Cultivation Grand Strategy Game\Cultivation GSG` via registered project `cultivation-gsg`.
- Historical/reference/staging areas: `Archive\`, `_staging\`, raw imports, pasted reports, old handoffs, superseded directions.
- Project-specific warnings: Raw memos are evidence, not canon; canon pages are decisions; implementation pages are build truth; archive and staging material are not active instructions by default.
- Open authority questions: Whether the code repo and wiki repo should remain separate registered projects, and which file should be the primary first-read when a task touches both.

### invading-cultivation-army

- Root: `C:\Users\gophe\AppData\Roaming\coe5\mods\Invading_Cultivation_Army`
- Configured summary/entry file: `PROJECT_STATUS.md`
- Actual first file to read: `PROJECT_STATUS.md`, then `README.md` and `docs\design\current-direction.md` when design context is needed.
- Current authority status: Registered live Conquest of Elysium 5 mod project; `Invading_Cultivation_Army.c5m` is the live source of truth unless explicitly superseded.
- Related external notes/spaces: `D:\GopherVault\10-Projects\Invading Cultivation Army.md`; intended GitHub remote is `https://github.com/Gopher697/Invading-Cultivation-Army.git`.
- Historical/reference/staging areas: `archive\` contains old experiments only; `References\coe5\`, `References\ergen\`, and `References\tools\` are source/reference material.
- Project-specific warnings: Do not replace the live `.c5m` with older assistant-generated test folders; do not delete archive or reference corpus material unless explicitly requested.
- Open authority questions: GitHub repository creation/push status depends on whether `Gopher697/Invading-Cultivation-Army` exists and local authentication can push.

## Cross-Project Warnings

- Project-specific assumptions should not leak into unrelated projects just because they appear in a shared vault, archive, or session note.
- GopherVault notes can be useful references, but they are not active Workbench authority unless explicitly configured, promoted, or mirrored into the authoritative location.
- Session notes are historical logs by default and should not be treated as canonical current state without explicit promotion.
- Archive, staging, pasted report, and old handoff material can contain stale, mixed-current, or unsafe instructions; treat them as evidence/reference by default.
- Separate code repo and wiki repo authority splits must be called out explicitly, especially for Cultivation GSG.
- More detailed notes should not outrank shorter configured entrypoint files solely because they contain more content.

## Registry Maintenance Rules

- Update this registry when projects are added, removed, renamed, or their entrypoints change.
- Do not update this registry based only on a session note unless the human confirms promotion.
- Do not use this registry to summarize project content.
- Keep entries short and authority-focused.
- Prefer linking to the project's real entrypoint over copying project details here.
- Preserve missing entrypoint and authority ambiguities instead of resolving them silently.
