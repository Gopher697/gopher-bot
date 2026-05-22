# Codex — Close C-006 in AGENT_COMMITMENTS.md

## Security invariant — check before every commit

`world_models/config.py` is gitignored and contains Neo4j credentials and API keys.
Run `git status` before committing. If `world_models/config.py` appears, STOP — do not commit.

---

## What to do

Edit `AGENT_COMMITMENTS.md` to formally close C-006. All five completion criteria are met
as of 2026-05-20:

1. ✅ BrainLoop packets carry `current_time`, `session_age_seconds`, `time_since_last_nrem`,
   `time_since_last_interaction` (Task 59)
2. ✅ Dream AUDIT runs `verify_chain()` every NREM cycle and logs result to DreamLog (Task 47)
3. ✅ OpenTimestamps `.ots` proof file written to `logs/audit/timestamps/` nightly (Task 61,
   commit ba14030)
4. ✅ Pattern Monitor behavioral baseline active; drift >2σ submits high-priority bid to
   Awareness (Task 56)
5. ✅ Mirror-Self self-model deviation logging active (Tasks 26, 60)

---

## Changes to make

### 1. C-006 table — change status and fix stale field name

In the C-006 table, make three changes:

**a.** Change the `status` row from:
```
| `status` | active |
```
to:
```
| `status` | closed |
```

**b.** Add a `closed` row immediately after the `status` row:
```
| `closed` | 2026-05-20 |
```

**c.** In the `completion_criteria` row, fix the stale field name.
The current text says `time_since_last_gopher_input` — the code uses `time_since_last_interaction`.
Replace the phrase:
```
time_since_last_gopher_input
```
with:
```
time_since_last_interaction
```
(This is the only occurrence that needs changing in that row.)

### 2. Update the header line

Change:
```
**Last updated:** 2026-05-20 (C-004 closed; C-006 added — temporal self-awareness + inner defense)
```
to:
```
**Last updated:** 2026-05-20 (C-004 closed; C-006 closed — all inner defender criteria met)
```

### 3. Add closure summary to "Closed Commitments" section

Append to the "Closed Commitments" section (after the C-004 closure paragraph, before `---`):

```
C-006 — closed 2026-05-20. All five completion criteria met: BrainLoop packets carry
temporal fields including time_since_last_interaction (Task 59, commit recorded);
Dream AUDIT runs verify_chain() autonomously each NREM cycle with DreamLog output
(Task 47); OpenTimestamps .ots proofs written to logs/audit/timestamps/ nightly (Task 61,
commit ba14030); Pattern Monitor baseline active with >2σ drift detection (Task 56);
Mirror-Self self-model deviation logging active (Tasks 26, 60). Inner defender loop closed.
Trust escalation protocol (Task 49) now unblocked.
```

---

## Verification

No tests required — this is a documentation-only change.

Confirm the file looks correct, then:

```
git status
```

`world_models/config.py` must NOT appear. Then commit:

```
git commit -m "governance: close C-006 — all inner defender criteria met (2026-05-20)"
```
