# Workbench Orientation SOP

## Purpose

Use this SOP for fresh or generic agent sessions that are not clearly inside a
registered project or repo.

Its purpose is to route the agent to the correct Workbench or project context
before planning, editing, cleanup, documentation, code changes, or other
project-specific work.

## When To Use This SOP

Use this SOP when:

- The current directory is empty.
- The current directory is not a git repo.
- The task mentions Workbench, MCP, project registry, wiki structure, SOPs,
  GopherVault, project routing, or cross-project notes.
- The agent is unsure which configured project owns the task.
- The user asks which project, session, or agent should handle something.
- The agent only sees MCP SOP resources but no repo-local files.

## Core Rule

Do not guess project context.

If project context is unclear, pause and identify the correct registered project
or ask for routing clarification before implementation.

## Orientation Steps

1. Check the current working directory and whether it is a git repo.
2. If inside a repo or project, look for repo-local `AGENTS.md` or project
   guidance.
3. If not inside a repo or project, use MCP and project context to identify
   likely registered projects.
4. For Workbench control-layer tasks, route to:

   `D:\gopher-workbench-mcp`

5. Once in the Workbench project context, read:

   - `D:\gopher-workbench-mcp\AGENTS.md`
   - `D:\gopher-workbench-mcp\WORKBENCH_INDEX.md`
   - `D:\gopher-workbench-mcp\PROJECT_REGISTRY.md`
   - `D:\gopher-workbench-mcp\KNOWLEDGE_SPACES.md`

6. For project-specific tasks, use `PROJECT_REGISTRY.md` to identify the correct
   project and its actual first file to read.
7. Do not start editing until the correct project context and authority files
   are identified.

## Routing Guide

- Workbench, index, registry, MCP, SOP, and global wiki structure tasks:
  `gopher-workbench-mcp`
- 5D Chess code, tests, tools, and docs: `5d-chess-tools`
- WorldBox XianNi mod work: `worldbox-xianni`
- Cultivation GSG design, wiki, and canon notes: `cultivation-gsg-wiki`
- Cultivation GSG code and prototype implementation: `cultivation-gsg`
- CoE5 Invading Cultivation Army mod files: `invading-cultivation-army`
- Broad GopherVault notes or memory questions: `gopher-vault`
- Sandbox or test tasks: `mcp-sandbox`

`PROJECT_REGISTRY.md` is the authority for current registered projects,
entrypoints, and ambiguity warnings.

## Authority Rules

- MCP configured projects are tool-access boundaries, not the whole wiki.
- `WORKBENCH_INDEX.md` is the Workbench front door.
- `PROJECT_REGISTRY.md` maps registered projects, entrypoints, and authority
  boundaries.
- `KNOWLEDGE_SPACES.md` explains the broader wiki and knowledge layers.
- Workbench-wide SOP authority lives in `D:\gopher-workbench-mcp\sops\`.
- GopherVault SOPs and project-local SOPs are reference or candidates unless
  promoted or mirrored into Workbench SOP authority.
- More comprehensive does not mean more authoritative.
- Session notes, staging folders, raw imports, pasted reports, archives,
  backups, and old handoffs are historical, evidence, or reference by default.
- Ambiguous authority should be flagged instead of silently resolved.
- Project-specific assumptions must not leak into unrelated projects.

## Safe Response Pattern

When using this SOP, first report:

1. Current working directory and whether it is a git repo.
2. Which registered project appears to own the task.
3. Which Workbench or project orientation files should be read next.
4. Whether the task is:
   - routing or orientation
   - Workbench control-layer work
   - project-specific implementation
   - project-specific wiki or notes work
   - broad GopherVault notes or memory work
   - risky cross-project work
5. Whether edits are safe to consider yet.

## Before Editing

- Do not edit from an empty or unclear scratch context.
- Do not perform broad cleanup as part of orientation.
- For implementation, prefer narrow one-file or one-task scopes.
- Before editing, state expected files to change.
- After editing, verify with `git status` or the appropriate project status
  check.
