# Agent Commitments

**Governed by:** Persistent Agent Charter (`AGENT_CHARTER.md`) Article VI
**Last updated:** 2026-05-18 (C-003 superseded; coordinator registry expanded to 14)
**Authority:** Chad Crouse (Gopher)

All entries must conform to the commitment shape defined in the charter. Entries that
cannot be expressed in this shape belong in GopherVault notes, not here.

---

## Active Commitments

### C-001 — Build governance foundation

| Field | Value |
|---|---|
| `id` | C-001 |
| `created` | 2026-05-18 |
| `owner` | gopher-workbench-mcp |
| `status` | active |
| `description` | Establish the governance layer of the neurosymbolic AI companion system: ratified charter, commitments file, proposals scaffold, bootstrap infrastructure, and workbench index registration. |
| `scope` | global — affects all coordinators and all future build work |
| `completion_criteria` | Charter ratified (done). AGENT_COMMITMENTS.md, proposals/pending/, proposals/resolved/, logs/actions/, and logs/pattern_observations/ all exist. WORKBENCH_INDEX.md or PROJECT_REGISTRY.md registers all governance files. First coordinator can complete Article IX startup sequence without freezing. |
| `review_trigger` | First live coordinator session (any coordinator completing Article IX startup) |
| `blocking_proposals` | none |

---

### C-002 — Build knowledge graph substrate

| Field | Value |
|---|---|
| `id` | C-002 |
| `created` | 2026-05-18 |
| `owner` | gopher-workbench-mcp |
| `status` | active |
| `description` | Design and implement the persistent knowledge graph that serves as the neurosymbolic brain's long-term memory. Candidates: Neo4j (richest graph queries), SQLite with relationship tables (local, portable), Datalog (rule-based inference). The graph stores world models, coordinator knowledge, and patterns across sessions. |
| `scope` | global — the persistent memory substrate for all coordinators |
| `completion_criteria` | At least one coordinator can read from and propose writes to the graph through the promotion mechanism. World model data survives session boundaries. |
| `review_trigger` | After first coordinator (beyond startup.py) reads from and writes to graph during a real session |
| `blocking_proposals` | none |

---

### C-003 — ~~Add TEACHING_MODE.md to GameAgentCore~~ *(superseded)*

| Field | Value |
|---|---|
| `id` | C-003 |
| `created` | 2026-05-18 |
| `owner` | game-agent-core |
| `status` | superseded |
| `description` | GameAgentCore will be absorbed into the main system when the Hands coordinator is operational. Game sessions become world model environments natively; game learning is the predict→act→compare→revise loop running through Hands and Memory. No separate teaching protocol is needed — the neurosymbolic architecture handles it. |
| `scope` | game-agent-core (absorbed into main system) |
| `completion_criteria` | n/a — superseded by C-004 follow-on work |
| `review_trigger` | When Hands coordinator is operational |
| `blocking_proposals` | none |

---

### C-004 — Build coordinator architecture and web interface

| Field | Value |
|---|---|
| `id` | C-004 |
| `created` | 2026-05-18 |
| `owner` | gopher-workbench-mcp |
| `status` | active |
| `description` | Build the full coordinator architecture on a self-hosted web interface (not Discord — privacy decision made 2026-05-18). Includes: async bid-gating Awareness hub, background brain loop running coordinators on independent cadences, all planned coordinators implemented as async workers, web UI for Chad interaction (voice + text), and audit panel for coordinator activity. Absorbs Vaultbot into Memory when Memory is operational. |
| `scope` | global — interface and coordinator execution layer for the whole system |
| `completion_criteria` | Background brain loop running alongside Flask. At least three background coordinators (Feeling, Pattern Monitor, Curiosity) submitting bids to Awareness independently of Chad input. Voice responding both reactively (to Chad messages) and proactively (from coordinator bids). Audit panel shows live coordinator activity. |
| `review_trigger` | After first proactive Voice output surfaces from background brain without Chad prompt |
| `blocking_proposals` | none |

---

## Closed Commitments

*(none yet)*

---

## Paused / Superseded

### C-003 moved here — see Active Commitments section above for full entry.

---

## Schema Reference

Every entry must carry all fields below. Entries that cannot be shaped this way
are notes — put them in GopherVault.

| Field | Description |
|---|---|
| `id` | Unique identifier (C-NNN) |
| `created` | Date created (YYYY-MM-DD) |
| `owner` | Project or domain |
| `status` | `active` / `paused` / `superseded` / `blocked` / `closed` |
| `description` | What is committed to |
| `scope` | Environment or project this applies to |
| `completion_criteria` | What evidence proves it is done |
| `review_trigger` | Date or condition that prompts review |
| `blocking_proposals` | Any pending proposal IDs that affect this |
