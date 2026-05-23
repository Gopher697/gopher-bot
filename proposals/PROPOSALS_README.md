# Proposals

**Governed by:** Persistent Agent Charter (`AGENT_CHARTER.md`) Article VI
**Authority:** Gopher (Gopher)

This directory is the promotion mechanism — the controlled path by which working-scratch
knowledge earns permanence in the system's durable layers (world models, commitments,
or the charter itself).

---

## Directory Structure

```
proposals/
  pending/     ← Active proposals awaiting human decision
  resolved/    ← Decided proposals (approved, rejected, or deferred)
```

---

## How It Works

1. A coordinator agent observes something worth preserving.
2. It creates a `.md` file in `proposals/pending/` using the schema below.
3. At the next session start (Article IX step 4), the coordinator surfaces pending proposals.
4. Gopher reviews and decides: `approved`, `rejected`, or `deferred`.
5. If approved, the coordinator writes the claim to its `destination_path`.
6. The proposal file is moved to `proposals/resolved/` with the decision fields filled in.

Proposals missing required fields are invalid and must not be acted on.

---

## Proposal Schema

Every file in `proposals/pending/` must contain all of the following fields:

| Field | Description |
|---|---|
| `id` | Unique identifier (e.g., `P-001`) |
| `created_at` | ISO datetime |
| `proposed_by` | Agent or tool name |
| `target_layer` | `world_model` / `commitments` / `charter` |
| `target_environment` | Game name, workspace name, or `global` |
| `proposed_claim` | The fact or abstraction being proposed |
| `evidence` | What was observed that prompted this |
| `prediction_made` | What this claim successfully predicted (if any) |
| `falsification_condition` | What would disprove this claim |
| `scope_limits` | Where this claim explicitly does NOT apply |
| `risk_level` | `low` / `medium` / `high` |
| `destination_path` | File path where this would be written if approved |
| `human_decision` | `pending` / `approved` / `rejected` / `deferred` |
| `decision_timestamp` | ISO datetime of decision |
| `decided_by` | Who made the decision (coordinator name or `Gopher`) |
| `decision_source` | Session, channel, or context where decision was made |
| `decision_statement` | Exact approval or rejection statement |
| `notes` | Free text |

---

## Template

Copy this to `proposals/pending/P-NNN.md` and fill in all fields:

```markdown
---
id: P-NNN
created_at: YYYY-MM-DDTHH:MM:SSZ
proposed_by: [agent/tool name]
target_layer: [world_model | commitments | charter]
target_environment: [environment name or global]
proposed_claim: >
  [The fact or abstraction being proposed]
evidence: >
  [What was observed]
prediction_made: >
  [What this successfully predicted, or "none yet"]
falsification_condition: >
  [What would disprove this]
scope_limits: >
  [Where this does NOT apply]
risk_level: [low | medium | high]
destination_path: [file path for the approved write]
human_decision: pending
decision_timestamp: ~
decided_by: ~
decision_source: ~
decision_statement: ~
notes: >
  [Optional free text]
---
```
