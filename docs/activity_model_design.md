# Activity Model Design

**Status:** Draft — approved for Codex implementation  
**Author:** Claude (Director)  
**Date:** 2026-05-25  
**Depends on:** P0-P4 bid priority system (can be partially implemented without it)

---

## Problem

The bot currently has no model of what it is doing at any given moment. It reacts to each
input in isolation. It does not know if it is mid-game, mid-task, mid-reminder, or
operating autonomously. Consequences:

- **Board/game state lost between turns** — reconstructed from context, unreliably
- **Reminders fail** — the bot acknowledges a reminder request but has no mechanism to
  fire it proactively; it only remembers when the user prompts it
- **Skill recording unwired** — `record_skill_practice()` exists but nothing calls it
  because nothing knows when a "practice session" is happening
- **Corrections don't suppress habitual patterns** — because the bot has no model of
  "I am currently playing chess and was corrected about mouse control," it cannot weight
  that correction above its background tendency
- **Parallel contexts break** — if the user asks a question from work while the bot
  runs an autonomous task at home, both contexts collapse into the same flat input stream

The Activity model is the **executive function layer** that fixes all of these.

### Design intent: general-purpose continuity for a systems AI

Gopher-bot is a systems AI — it handles work tasks, research, creative projects,
personal productivity, home automation, monitoring, reminders, and games. The Activity
model applies equally to all of these. A research task running in the background while
the user is at work, a multi-step document workflow, a long-running project that spans
weeks, a monitoring condition, a reminder to follow up on something — all activities,
all tracked the same way.

The gaming use case surfaced the need for this architecture, but it is not the primary
use case. Work continuity is equally important, possibly more so.

Gopher-bot is also explicitly designed to compensate for an ADHD user who is time-blind
and prone to dropping threads across all domains — not just games. A project half-done,
a research thread abandoned, a task started and forgotten — these are exactly what the
dormant activity lifecycle and Dream's TRIAGE surfacing are designed to recover. The
system remembers and holds context so the user doesn't have to carry it mentally.

---

## Core Concept

An `Activity` is a structured, ongoing context the bot recognizes it is participating in.
It is distinct from an `Observation` (which is a fact about the world, immutable once
written) and distinct from a `Bid` (which is a request for action, ephemeral).

An Activity:
- Has a **type** that determines how the bot should behave
- Has **mutable state** — updated throughout its lifecycle
- Has **goals** — what success looks like
- Has **skill domains** — what capabilities are being exercised
- Has a **lifecycle** — created, active, paused, completed, abandoned
- Can be **nested** — a chess game inside a conversation
- Can be **parallel** — autonomous task at home + user conversation from work

---

## Neo4j Node Schema

```cypher
(:Activity {
    id:             string,       // uuid
    environment:    string,       // matches Memory environment partitioning
    type:           string,       // see Activity Types below
    name:           string,       // human-readable label, e.g. "chess game 2026-05-25"
    status:         string,       // "active" | "paused" | "completed" | "abandoned"
    created_at:     float,        // unix timestamp
    updated_at:     float,
    completed_at:   float | null,
    trigger_at:     float | null, // for reminder type: when to fire
    goals:          string,       // JSON list of goal strings
    skill_domains:  string,       // JSON list of domain strings
    state:          string,       // JSON dict — mutable game/task state
    parent_id:      string | null // for nested activities
})
```

Relationships:
```cypher
(:Activity)-[:GENERATED]->(:Observation)   // observations produced during this activity
(:Activity)-[:EXERCISED]->(:SkillNode)     // skills being practiced
(:Activity)-[:CHILD_OF]->(:Activity)       // nesting
```

---

## Activity Types

| Type | Description | State contents | Skill domains |
|---|---|---|---|
| `game` | Any game being played | `{"fen": "...", "moves": [...], "game_id": "..."}` | `["chess"]` or detected game name |
| `task` | Discrete computer task | `{"goal": "...", "steps_done": [...], "step_current": "..."}` | `["computer_use"]` |
| `reminder` | Time-triggered action | `{"message": "poke the button", "trigger_at": 1234567}` | `[]` |
| `autonomous` | Bot operating without user | `{"objective": "...", "progress": 0.0-1.0}` | varies |
| `monitoring` | Watch condition, alert on change | `{"condition": "...", "last_check": ts, "alerted": false}` | `[]` |
| `conversation` | General conversation | `{}` | varies |

---

## Lifecycle

```
Recognition → Created → Active ↔ Dormant → Completed
```

There is no "abandoned" status. Activities that go quiet become **dormant** — they age
in episodic memory exactly like any other observation, weighted by recency. Dream
surfaces dormant activities during TRIAGE ("you have unfinished threads"). When context
signals matching a dormant activity reappear (chess FEN after weeks away), Awareness
resumes it seamlessly. Activities are only `completed` when a completion signal is
explicitly detected or triggered.

This is intentional: the system compensates for context-dropping by never discarding
context itself. Dormant ≠ dead.

**Recognition** — Awareness scans the packet for activity signals (see below). Checks
the activity registry for an existing instance matching the context key. If found and
dormant, resumes it. If active, continues it. If none found, creates a new one.

**Created** — Activity node written to Neo4j. Registry updated with `(type, context_key)
→ activity_id`. BrainLoop sets it as foreground.

**Active** — Each turn, Orientation injects the current activity into the operational
context so Reason knows what it is doing. Hands updates `Activity.state` after executing
actions. Reason checks `activity.type` to decide whether to call `record_skill_practice()`.

**Dormant** — When no matching context signal arrives for a while, or when a different
activity becomes foreground, the previous activity becomes dormant (`status = "dormant"`,
`updated_at` set). Its full state is preserved in Neo4j. No data is lost.

**Resumed** — Context signals match a dormant activity → Awareness retrieves it,
restores state from Neo4j, updates status to `active`. The bot picks up where it left
off regardless of how much time has passed.

**Completed** — Awareness or Reason detects a completion signal (game over, task
finished, reminder fired). Activity marked completed. SkillNode records outcome.
Completed activities remain in the graph as episodic history.

---

## Activity Recognition Signals

Implemented in a new `_detect_activity(packet)` method in Awareness, called before
Memory retrieval so that the detected activity can influence what Memory surfaces.

| Signal | Detected by | Activity created |
|---|---|---|
| Chess FEN string in message | regex: FEN pattern | `game` with `skill_domains=["chess"]` |
| Board image + chess context | VLM description contains "chess board" | `game` with `skill_domains=["chess"]` |
| "remind me in X" / "at X time" | regex: reminder intent phrases | `reminder` with `trigger_at` computed |
| Game window detected by OmniParser | game executable in window list | `game` with game name from window title |
| Autonomous task assignment | no user present + task instruction | `autonomous` |
| Explicit task assignment | "do X on my computer" patterns | `task` |
| No other signals | fallback | `conversation` |

Detection is **non-destructive** — if an active activity of the matching type already
exists and is not completed, Awareness retrieves it rather than creating a new one.

---

## Coordinator Changes

### Awareness

New method: `_detect_activity(packet) -> Activity | None`

- Runs before Memory retrieval
- Writes activity signals to `packet["current_activity"]` as a dict
- Creates or retrieves Activity node in Neo4j

New method: `_check_scheduled_activities()` — called in `background_tick()`

- Queries Neo4j for Activity nodes with `type="reminder"`, `status="active"`,
  `trigger_at <= now()`
- For each due reminder: submits P1 bid to Voice with the reminder message
- Marks the Activity as completed

### Orientation

`_operational_context()` gains a new section when `packet["current_activity"]` is set:

```
Activity: chess game (active)
  State: FEN r1bqk2r/pppp1ppp/...
  Move history: 1.e4 e5 2.Nf3 Nc6
  Goals: play legal chess, improve positional play
  Skills: chess
```

This replaces the need for the bot to reconstruct game state from context. It reads
current state at every turn from the Activity node.

### Hands

New method: `_update_activity_state(activity_id, state_patch)` — called after executing
actions that change game/task state.

- Merges `state_patch` into `Activity.state` (JSON dict merge, not replacement)
- Updates `Activity.updated_at`

For chess: after the bot declares a move, Hands writes the new FEN and appended move to
the activity state.

### Reason

After generating a response, checks `packet["current_activity"]["type"]`:
- If `"game"` or `"learning"`: calls `record_skill_practice()` with the activity's
  skill domains, the action taken, and outcome if determinable
- Outcome is "unknown" if not determinable in the turn — Dream can infer it later

### Memory

`retrieve()` gains awareness of the current activity:
- If `current_activity.type == "game"`, weight retrieval toward the game's skill domain
- Pull the most recent active Activity node of the matching type as a priority retrieval
  (above the standard two-lane system)

### BrainLoop

Maintains an **activity registry** as an in-memory dict:
```python
# (type, context_key) → activity_id
_activity_registry: dict[tuple[str, str], str]
# ordered by last_active for foreground determination
_activity_order: list[tuple[str, str]]
```

`foreground_activity_id` = registry entry with most recent `last_active` timestamp.

Multiple parallel instances of the same type are fully supported — a chess game and a
Factorio session are separate registry entries with different context keys. The bot
tracks all of them; foreground is simply whichever was touched most recently.

On each turn: reads the foreground activity from Neo4j. On `background_tick()`:
calls `_check_scheduled_activities()` via Awareness.

---

## The Reminder Problem (Proactive Messaging)

The chess session exposed a gap: the bot can acknowledge a reminder but cannot fire it
without an incoming message to trigger a turn. Fix:

`BrainLoop.background_tick()` calls `Awareness._check_scheduled_activities()` on every
tick. When a reminder's `trigger_at` has passed, Awareness submits a P1 bid directly
to the bid queue with the reminder content. BrainLoop processes it as a turn, Voice
sends the Discord message. No incoming message required.

This requires BrainLoop's autonomous turn processing to be wired to Voice output —
verify this is already the case for Dream/Curiosity autonomous turns.

---

## Relationship to P0-P4 Bid Priority

Activity type maps to natural bid priority:

| Activity type | Bid priority | Rationale |
|---|---|---|
| `reminder` trigger | P1 CAPTURE | User-committed, time-sensitive |
| `game` turn (user present) | P1 CAPTURE | Active engagement |
| `task` step | P2 HEALTH | Progress matters, not time-critical |
| `autonomous` step | P3 INSIGHT | Background work |
| `monitoring` alert | P1 CAPTURE | User needs to know |
| `conversation` | P1 CAPTURE | User is present |

The P0-P4 system can be implemented after the Activity model — the Activity model does
not require it. But P0-P4 is what makes the activity stack actually preempt correctly
when multiple activities compete for BrainLoop CPU.

---

## Skill Recording Integration

Currently `record_skill_practice()` exists in the codebase but is called nowhere
(flagged in backlog). With the Activity model:

- Any `game` or `learning` activity **automatically** triggers skill recording each turn
- No per-game wiring required — the activity type drives it universally
- Skill domain comes from `activity.skill_domains` (e.g. `["chess"]`)
- Outcome: immediate outcome if detectable (checkmate = loss), else "pending" — Dream
  resolves pending outcomes during consolidation by reading activity history

---

## Implementation Sequence (for Codex)

Split into two Codex tasks to keep diffs reviewable:

**Task A — Schema + Recognition (no coordinator changes)**
- Add `Activity` node type to world model
- `Awareness._detect_activity()` with recognition signals
- `Awareness._check_scheduled_activities()` for reminder firing
- BrainLoop activity stack (in-memory only in this task)
- Tests: recognition signals → correct activity type; reminder fires via background_tick

**Task B — Coordinator wiring**
- Orientation: inject current activity into operational context
- Hands: `_update_activity_state()` after actions
- Reason: auto-call `record_skill_practice()` for game/learning activities
- Memory: activity-aware retrieval weighting
- Tests: full turn with active game activity → state updated, skill recorded, context injected

---

## Design Decisions (Resolved)

1. **Activity persistence across restarts** — Resolved: activities persist in Neo4j
   indefinitely. On restart, Awareness loads active/dormant activities from Neo4j into
   the registry. Old activities are not deleted — they age in episodic memory and can
   be resumed whenever matching context reappears, even weeks or months later. There is
   no expiry.

2. **Activity name generation** — Resolved: auto-generated by the system from type +
   context signals + timestamp. E.g. "chess · Ruy Lopez · 2026-05-25". User does not
   name activities; naming should aid retrieval, not require effort.

3. **Staleness threshold** — Resolved: no fixed threshold. Dormant activities use the
   same recency weighting as all other episodic memory — more recent = more accessible,
   but never discarded. Dream surfaces dormant activities during TRIAGE regardless of
   age. The system is designed to compensate for context-dropping, not penalize it.

4. **Multiple parallel instances** — Resolved: the activity registry is a dict keyed
   by `(type, context_key)` supporting arbitrary parallelism. Foreground = most recently
   active. All others remain tracked and resumable. This matters: the user maintains
   many parallel threads across games, tasks, and projects, and the system must handle
   all of them without collision or data loss.
