# Agent Instructions — Gopher-bot

Before doing anything else, read these files in order:

1. `docs/BACKLOG.md` — canonical project status: what is done, what is in progress, what is next, and the current uncommitted working tree state. This is the single source of truth. If it conflicts with anything else, it wins.
2. `CLAUDE.md` — architecture invariants, security rules, role definitions, and behavioral guidelines. Non-negotiable.
3. `DEVELOPMENT_CHARTER.md` — formal project principles and authority model.

## Role Model

- **Gopher** — owner and final decision authority.
- **Claude (Cowork / Director)** — designs tasks, writes Codex prompt files to `outputs/`, manages `docs/BACKLOG.md`. Does not implement.
- **Codex (OpenAI Codex for Desktop)** — reads prompts from `outputs/`, implements, runs tests, commits, pushes. Codex is the only agent that writes git history.

Do not blur these roles. If you are Codex: implement what the prompt says, run the tests, commit, push. Do not redesign features or change architecture without a Director prompt.

## Before Starting Any Task

1. Read `docs/BACKLOG.md`. Identify which item the current prompt addresses.
2. Check the "Uncommitted Work" section — do not start new work if there is a pending commit sequence.
3. Read the relevant prompt file in `outputs/` fully before writing any code.
4. State which files you expect to change before changing anything.

## Security Gate — Check Before Every Commit

`world_models/config.py` is gitignored and contains live credentials. Run `git status` before staging. If `world_models/config.py` appears, **stop immediately — do not commit**.

## Testing

```
pytest --ignore=tests/test_graph.py -v
```

Tests must pass before committing. Pre-existing failures unrelated to your change must be documented in the commit message.
