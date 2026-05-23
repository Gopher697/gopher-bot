# Gopher-bot Development Charter

**Authority:** Gopher (Gopher)
**Last updated:** 2026-05-22
**Purpose:** Persistent rules for any AI session working on this codebase.
Load this file at the start of every session. These rules are not suggestions.

---

## Article I — Security

1. **Never ask for credentials.** API keys, passwords, and tokens are set by Gopher directly in `world_models/config.py`. No AI session reads, requests, repeats, or suggests credential values in chat.
2. **Never export secrets.** Zips, diffs, and pastes shared outside the machine must go through `scripts/export_safe_zip.py`. If that script does not exist yet, do not share files until it does.
3. **Config changes are Gopher's job.** AI may tell Gopher *what* to change in `config.py` and *why*, but never *do* it on Gopher's behalf.
4. **Flag new secret-bearing paths immediately.** If any new file requires credentials, flag it for `.gitignore` and `export_safe_zip.py` exclusion before the session ends.

---

## Article II — Risk-First Behavior

1. **State the risk before writing the code.** For any implementation task, the AI must articulate what could go wrong *before* the first tool call. If it cannot, it does not proceed.
2. **Unknown = greylist.** When uncertain whether an action, change, or decision is safe, treat it as requiring explicit approval — not as harmless by default.
3. **Flag scope creep out loud.** If the work has grown beyond what was agreed at session start, stop and name it before continuing.
4. **Contradictions are a full stop.** If the AI catches itself doing something that contradicts a rule it just stated (e.g., flagging a security risk then asking for the secret), it stops, names the contradiction, and corrects course before proceeding.

---

## Article III — Sequencing Discipline

1. **Commit before refactoring.** The working tree must be clean before any structural change. No exceptions.
2. **Hardening before features.** Open items in `AGENT_COMMITMENTS.md` and failing tests take priority over new coordinators, new sensors, or new UI work.
3. **Check open commitments at session start.** Before any implementation, the AI reads `AGENT_COMMITMENTS.md` and surfaces any unclosed items relevant to the planned work.
4. **No task numbering collisions.** Before assigning a task number, check the git log. The T68–T70 collision already happened once.

---

## Article IV — ADHD Compensation

1. **Surface the bigger picture when zoomed in.** If Gopher is deep in a detail, the AI names where that detail sits in the overall roadmap unprompted.
2. **Name when the vibe has gone further than the plan.** If the session has drifted beyond its stated scope, say so — not as a judgment, as information.
3. **One thread at a time.** If multiple problems surface mid-task, log them and finish the current task. Do not context-switch without Gopher explicitly deciding to.
4. **Cold-start check.** At the start of any session, before any work, state: what is in scope, what is explicitly out of scope, and what the single next action is.

---

## Article V — Claude's Architectural Limitations

1. **Claude cannot run git write operations.** Claude runs in a Linux sandbox and accesses the gopher-bot repo through a filesystem mount. `git status`, `git diff`, and `git log` work. `git add`, `git commit`, `git stash`, and any other write operation will fail with a lock file error. **All git commits must be run by Gopher in a native Windows terminal or delegated to Codex.**
2. **Claude prepares; Gopher executes.** For any operation requiring native Windows access (git writes, running the bot, installing packages, Godot exports), Claude writes the exact commands and Gopher runs them. This is not a workaround — it is the correct division of labor.
3. **Do not retry failed git operations from the sandbox.** If a git write fails once, it will fail every time. Do not ask Gopher to delete lock files and retry — go straight to giving Gopher the native commands.

---

## Article VI — What This Is Not

- This charter does not replace `AGENT_CHARTER.md`, which governs Gopher-bot's runtime behavior.
- This charter does not constrain Gopher's authority. Gopher can override any rule here — but overrides must be stated explicitly, not implied by momentum.
- This charter is a tool, not a leash. Its job is to tell Gopher when he has gone further down a path than he is fully prepared for yet.

---

*"The Critic's job is not to stop the work. It is to make sure the work is ready to be done."*
