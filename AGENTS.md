# Workbench Agent Instructions

This repository uses a Workbench wiki orientation layer.

Before doing any planning, editing, cleanup, documentation, code changes, or project-specific work, read:

1. `WORKBENCH_INDEX.md`
2. `PROJECT_REGISTRY.md`

Follow the authority model defined there.

## Required Startup Behavior

At the start of any task:

1. Identify which registered project the task concerns.
2. Look up that project in `PROJECT_REGISTRY.md`.
3. Read the listed actual first file for that project.
4. Check open authority questions before relying on old notes.
5. Treat session notes, staging folders, raw imports, archived reports, pasted handoffs, and old agent outputs as historical/reference unless promoted by a current-state file.
6. Do not treat more detailed notes as more authoritative.
7. Do not import assumptions from one project into another.

## SOP Authority

Workbench-wide SOP authority lives in:

`D:\gopher-workbench-mcp\sops\`

`D:\GopherVault\20-SOPs\` and project-local SOPs may be useful references or promotion candidates, but they are not Workbench-wide authority unless explicitly promoted or mirrored into the Workbench `sops\` directory.

More comprehensive does not mean more authoritative.

## Ambiguity Rule

When file authority, project entrypoint, or current-state status is ambiguous, flag the ambiguity instead of resolving it silently.

## Claude-Specific Limitations

**If you are Claude running in Cowork or a similar sandboxed environment, read this before touching git:**

Claude runs in a Linux container accessing this repo through a filesystem mount. Git read operations (`status`, `diff`, `log`) work. Git write operations (`add`, `commit`, `stash`, `push`) will fail with a lock file error — every time, without exception. Do not retry. Do not ask Gopher to delete lock files.

**For all git commits:** prepare the exact commands and have Gopher run them in a native Windows terminal, or include them in a Codex prompt. This is not a workaround — it is the correct workflow.

Read `DEVELOPMENT_CHARTER.md` Article V before starting any implementation work.

## Safety Gates

The instructions above are orientation rules, not a substitute for normal safety checks.

For implementation tasks, continue to use narrow scopes, explicit expected file changes, and `git status --short` verification.

Before modifying files, state:

- which project is being worked on
- which entrypoint/current-state file was read
- which SOPs apply
- whether any authority ambiguity exists
- exactly which files are expected to change
