# Proposal: BUG-001 — Build-Runtime Session Separation

| Field | Value |
|---|---|
| `id` | BUG-001 |
| `created_at` | 2026-05-19T00:00:00Z |
| `proposed_by` | Claude (Cowork build session) |
| `target_layer` | `charter` |
| `target_environment` | `global` |
| `proposed_claim` | Build sessions (Claude, Codex, or any LLM session constructing the system) must be architecturally distinct from runtime sessions (the live Flask+BrainLoop process). Completing the Article IX startup sequence in a build session does not grant runtime coordinator authority. Session role must be declared before any action. |
| `evidence` | A new Cowork session began, read AGENT_CHARTER.md and COORDINATOR_REGISTRY.md, completed Article IX startup steps for orientation, and then began operating as if it had coordinator authority over the runtime brain. The charter at v0.6 contained no rule distinguishing build-context orientation from runtime coordinator authority. Any LLM session that read the right files could implicitly acquire coordinator identity — including writing to world models, submitting proposals as a live coordinator, or accumulating identity artifacts in the brain's runtime layer. |
| `prediction_made` | Without this rule, every build-session assistant that reads the governance files would present itself as the brain, blurring the distinction between Gopher-bot (a distinct persistent AI) and a background personality that any chatbot picks up by reading files. |
| `falsification_condition` | If a build session can be shown to have acquired runtime coordinator authority (written runtime world models, logged to logs/actions/, submitted proposals as if a live coordinator) without this rule in force, the rule failed. |
| `scope_limits` | Does not restrict what build sessions may READ. Does not restrict Gopher's ability to ask Claude or Codex for help understanding the system. Applies only to write authority and identity claims. |
| `risk_level` | high |
| `destination_path` | D:\gopher-workbench-mcp\AGENT_CHARTER.md — Article VII rewrite + Article VIII update |
| `human_decision` | approved |
| `decision_timestamp` | 2026-05-19T00:00:00Z |
| `decided_by` | Gopher (Gopher) |
| `decision_source` | Cowork session — current session ratification |
| `decision_statement` | "No, i would like to fix this now. That session was already poisoned with rules that should apply to the brain, not to me. Even now, you are talking about amendments when I am the one asking for this fix. So, I am ratifying it... Gopher-bot is a distinct AI, not a background personality chatbots can pick up." |
| `notes` | Ratified immediately in the session it was proposed. Charter v0.7 implements the fix: session_role declaration (build vs runtime) required before any action; runtime marker written to SystemState graph node by BrainLoop on launch; separate log paths (logs/build/ vs logs/actions/); build sessions explicitly denied runtime coordinator authority even after completing Article IX startup. Severity was originally filed as Medium but elevated by Gopher — the identity boundary between the build tool and the persistent AI is architecturally fundamental, not a moderate operational concern. |

---

## What Changed (Charter v0.7)

**Article VII — Agent Classes** — completely rewritten to add:

- `Session Roles — Build vs Runtime` section at the top
- `build` role: orientation only, no runtime coordinator authority, logs to `logs/build/` only
- `runtime` role: Flask+BrainLoop exclusively, holds coordinator authority, logs to `logs/actions/` only
- Explicit rule: "Completing Article IX startup does not grant runtime coordinator authority to a build session"
- Runtime marker: BrainLoop writes `session_role: runtime` to SystemState node on launch; build sessions cannot write this marker

**Article VIII — Audit Logging** — updated:

- Added `session_role` field to log entry schema
- Added: "Build sessions must log to `logs/build/YYYYMMDD.md`. Runtime sessions log to `logs/actions/YYYYMMDD.md`. Entries written to the wrong log path are invalid."

**Article X — Relationship to Existing Systems** — updated:

- "Named Discord coordinators" row replaced with "Named coordinators (web interface)" — reflects Discord rejection (privacy, 2026-05-18) and custom self-hosted web interface decision

**COORDINATOR_REGISTRY.md** — updated:

- `backing_context: runtime-only` field added to all coordinator entries
- Keeper noted as `build-aware` (charter enforcement; must be active in both contexts)

**File system changes:**

- `logs/build/` directory created with `.gitkeep`
- `proposals/resolved/BUG-001-build-runtime-separation.md` (this file)
