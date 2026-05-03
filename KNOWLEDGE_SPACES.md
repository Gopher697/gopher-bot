# Workbench Knowledge Spaces

## Purpose

This file maps the Workbench's broader knowledge/wiki layers so future agents can orient across the system without confusing operational access, project memory, and authority.

- `WORKBENCH_INDEX.md` is the front door.
- `PROJECT_REGISTRY.md` maps configured projects, entrypoints, and authority boundaries.
- `KNOWLEDGE_SPACES.md` explains how the broader notes/wiki ecosystem is layered.
- `config\projects.yaml` is MCP operational access/configuration, not the whole wiki.

This is a connective-tissue file, not a project summary file.

## Layer 1: Workbench Control Layer

The Workbench control layer lives in:

- `D:\gopher-workbench-mcp\AGENTS.md`
- `D:\gopher-workbench-mcp\WORKBENCH_INDEX.md`
- `D:\gopher-workbench-mcp\PROJECT_REGISTRY.md`
- `D:\gopher-workbench-mcp\sops\`

This layer controls orientation, authority order, project boundaries, and Workbench-wide SOP authority. Agents should start here before relying on more detailed notes elsewhere.

## Layer 2: MCP Configured Project Access

MCP configured project access is defined by:

- `D:\gopher-workbench-mcp\config\projects.yaml`

This file controls which folders are configured for MCP tool access. MCP registration means a folder is configured and accessible by tools; it does not mean every note inside that folder is canonical.

Do not treat `config\projects.yaml` as the whole wiki. For the human/agent-readable project map, entrypoints, and authority boundaries, use `PROJECT_REGISTRY.md`.

## Layer 3: Project Workspaces and Repositories

Project workspaces and repositories are where implementation, code, mod files, tests, project docs, and project-local notes live.

Examples include:

- 5D Chess Tools
- WorldBox XianNi
- Cultivation GSG code repo
- Invading Cultivation Army CoE5 mod

These spaces are project-specific. Do not import assumptions from one workspace or repository into another without an explicit relationship from the registry, index, or current human task.

## Layer 4: Project-Specific Wikis

Some projects may have deeper wiki or memory spaces.

`cultivation-gsg-wiki` is one project-specific wiki. It is not the center of the whole Workbench and should not be treated as the master wiki for unrelated projects.

Project-specific wikis may hold canon, design memory, or current-state pages for their own project only, subject to the entrypoint and authority rules in `PROJECT_REGISTRY.md`.

## Layer 5: GopherVault External Memory

`D:\GopherVault` is a broad external notes/memory space.

It may contain:

- project notes
- SOP candidates
- prompts
- game notes
- archives
- project wiki material
- reference material

GopherVault material is reference/candidate material unless a specific file is configured, promoted, mirrored, or identified by an authoritative Workbench/project file.

More comprehensive does not mean more authoritative.

## Layer 6: SOP Authority and SOP Candidates

Workbench-wide SOP authority lives in:

- `D:\gopher-workbench-mcp\sops\`

GopherVault SOPs and project-local SOPs may be useful references or promotion candidates. They do not automatically become Workbench-wide authority by being more detailed.

Use project-local SOPs only within their project unless they have been explicitly promoted or mirrored into Workbench-wide SOP authority.

## Layer 7: Historical, Raw, Staging, and Archive Material

These materials are evidence/reference by default:

- session notes
- `_staging` folders
- raw imports
- pasted reports
- archived reports
- old handoffs
- old Codex/Claude outputs
- backups

Agents should not treat these as active instruction unless promoted by a current-state or authority file.

Current-seeming details in historical material can still be stale, mixed with superseded decisions, or scoped to a different project.

## Cross-Reference Rules

- Cross-reference projects only when the registry, index, or current human task makes the relationship relevant.
- Do not import assumptions from one project into another.
- Flag authority ambiguity instead of resolving it silently.
- Prefer authoritative entrypoints over longer historical notes.
- More comprehensive does not mean more authoritative.

## Common Confusions To Avoid

- MCP configured project list is not the whole wiki.
- `cultivation-gsg-wiki` is not the center of the Workbench.
- GopherVault breadth is not the same as authority.
- Session notes can contain current-seeming facts but are historical by default.
- Project-local SOPs are not Workbench-wide SOPs unless promoted.
- Code repo truth and wiki/project-memory truth may be split and should be flagged if ambiguous.

## When To Update This File

Update this file when:

- a new major knowledge layer is added
- the relationship between Workbench, GopherVault, project wikis, or MCP config changes
- SOP authority rules change
- cross-project reference rules change

Do not update this file for ordinary project progress.
