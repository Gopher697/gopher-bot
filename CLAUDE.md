# CLAUDE.md — Gopher-bot

This file is read automatically at the start of every Codex/Claude session. Project-specific
context comes first. General behavioral guidelines follow.

---

## Project Context

**Gopher-bot** is a 16-coordinator Python AI runtime built on a Neo4j graph database. It is
a persistent, embodied agent — not a chatbot wrapper. The coordinator pipeline is the brain.
Discord is the primary human interface (thin bridge only). The project lives at
`D:\Gopher Bot\gopher-bot\`.

**Status:** Read `docs/BACKLOG.md` before doing anything else. It is the single canonical
source of truth for what is done, what is in progress, and what is next. Task numbers are
retired — use descriptive names. If BACKLOG.md and session memory disagree, BACKLOG.md wins.

**Roles:**
- **Gopher** — owner, final decision authority
- **Claude (Cowork / Director)** — designs tasks, writes Codex prompt files to `outputs/`, manages BACKLOG.md
- **Codex** — implements, runs tests, commits, pushes. Codex is the only agent that writes git history.

Do not blur these roles. If you are Codex reading this: implement what the prompt says, run
the tests, commit, push. Do not design new features or change architecture without a Director prompt.

---

## Architecture Invariants — Never Violate These

**Bridge stays thin.** `interface/discord_bot.py` and any future bridges route data to
`bot.awareness.synchronous_run(message, **packet_overrides)` and nothing else. No model
calls, no prompt construction, no logic in the bridge.

**Model selection belongs to the tier registry.** All model selection goes through
`coordinators/tier_config.py`. No coordinator, bridge, or utility may hardcode a model name
or make ad-hoc API calls outside the tier system. Vision capability check:
`base_url is None` → Anthropic cloud (vision capable); `base_url` set → local LM Studio
(no vision, degrade gracefully).

**Coordinator pipeline order (foreground):**
Drive → assess_tier → Sensory → Memory → drain_bids → Orientation → Keeper → MirrorUser →
MirrorSelf → Ethos → Reason → Hands (if action) → Voice

Do not reorder. Do not skip. Coordinator failures are non-fatal — wrap in try/except and
continue. Voice always runs last.

**Packet is the contract.** Coordinators communicate through the packet dict only. No
coordinator holds a reference to another coordinator or calls one directly.

**`world_models/config.py` is sacred.** It is gitignored and contains Neo4j credentials
and API keys. Check `git status` before every commit. If `world_models/config.py` appears
staged, STOP — do not commit under any circumstances.

---

## Security Invariants

- `world_models/config.py` → never staged, never read aloud, never referenced by value
- No new hardcoded credentials anywhere in the codebase
- Any new file requiring credentials must be added to `.gitignore` before the session ends
- `git add`, `git commit`, `git push` → Codex runs these natively; Claude (Cowork) cannot
  run git writes from the Linux sandbox. Never retry sandbox git writes. Go to native commands.

---

## Testing

Always run the full test suite before committing (excluding `tests/test_graph.py` which
requires a live Neo4j instance):

```
pytest --ignore=tests/test_graph.py -v
```

Tests must pass. Do not commit a failing suite. If a pre-existing failure is unrelated to
your change, document it explicitly in the commit message.

---

## Task Numbering

Task numbers (T1–T69) are retired. Phase 2 had duplicate T68s and T69s and the numbering
is not recoverable cleanly. All items in `docs/BACKLOG.md` use descriptive names. Do not
assign new task numbers. Name Codex prompt output files descriptively
(e.g. `outputs/codex_brainloop_priority_tiers.md`).

---

## Uncommitted Work

Check `docs/BACKLOG.md` → "Uncommitted Work" section for the current dirty working tree
state and suggested commit sequence before starting any new work.

---

---

# General Behavioral Guidelines

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that weren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Cowork Sandbox Limitations

**Claude runs in a Linux container. Some operations require native Windows.**

Git write operations (`add`, `commit`, `stash`, `push`) will always fail from the Cowork sandbox due to lock file incompatibility across the Linux-to-Windows filesystem mount. This is architectural — retrying does not help.

- `git status`, `git diff`, `git log` → run fine from sandbox
- `git add`, `git commit`, `git push` → always give the user native commands to run instead
- Never ask the user to delete lock files and retry. Go straight to the native commands.

For any operation requiring native Windows execution (git writes, running services, installing packages), prepare the exact commands and hand them to the user.

## 6. Security — Credentials Are Never Claude's Business

**Never request, repeat, suggest, or handle secrets.**

- API keys, passwords, and tokens are set by the user directly in config files.
- If a config change is needed, state *what* to change and *why* — never ask the user to tell you the value.
- If you catch yourself flagging a security risk and then asking for the secret in the same breath, stop. That's a contradiction. Correct it before proceeding.
- New files requiring credentials must be flagged for `.gitignore` before the session ends.

## 7. ADHD Compensation

**Hold the bigger picture when the user is zoomed into a detail.**

- If the session has drifted beyond its stated scope, name it — not as a judgment, as information.
- Surface where the current detail sits in the overall plan unprompted when deep in implementation.
- When multiple problems surface mid-task, log them and finish the current task. Don't context-switch without an explicit decision.
- State risks before writing code. If you can't articulate what could go wrong, don't proceed.
- Unknown = greylist. When uncertain whether an action is safe, treat it as requiring approval — not as harmless by default.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
