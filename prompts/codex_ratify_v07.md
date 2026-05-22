# Codex Prompt — Ratify Charter v0.7

## Task

Stage and commit all files changed for the Persistent Agent Charter v0.7 amendment.
This is a build-session task. Log your actions to `logs/build/YYYYMMDD.md` (today: 2026-05-19).

## What was changed (stage all of these)

- `AGENT_CHARTER.md` — Article VII rewritten (build vs runtime session roles); Article VIII updated (session_role log field + separate log paths); Article X updated (Discord row replaced with web interface row); v0.7 amendment log entry added; header version and ratification date set
- `COORDINATOR_REGISTRY.md` — backing_context field added to every coordinator entry; version bumped to v6
- `logs/build/.gitkeep` — new file; creates the build session log directory required by charter v0.7
- `proposals/resolved/BUG-001-build-runtime-separation.md` — new file; resolved proposal documenting the build-runtime separation fix

## Steps

1. From the repo root (`D:\gopher-workbench-mcp`), run:

```
git add AGENT_CHARTER.md COORDINATOR_REGISTRY.md logs/build/.gitkeep proposals/resolved/BUG-001-build-runtime-separation.md
```

2. Verify the staged files look correct:

```
git diff --cached --stat
```

3. Commit with this exact message:

```
git commit -m "ratify: Persistent Agent Charter v0.7 — build-runtime separation"
```

4. Report back:
   - The full commit hash (short form is fine)
   - The files included in the commit
   - Any errors encountered

## Important constraints

- Do NOT stage or commit `world_models/config.py` — it is gitignored and contains secrets
- Do NOT push — that requires separate Tier 2 approval
- Do NOT modify any of the staged files — commit as-is
- Log this build action to `logs/build/20260519.md` with your session_role declared as `build`
