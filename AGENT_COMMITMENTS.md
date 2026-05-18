# Agent Commitments

**Governed by:** Persistent Agent Charter (`AGENT_CHARTER.md`) Article VI
**Last updated:** 2026-05-18
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
| `status` | blocked |
| `description` | Design and implement the persistent knowledge graph that serves as the neurosymbolic brain's long-term memory. Candidates: Neo4j (richest graph queries), SQLite with relationship tables (local, portable), Datalog (rule-based inference). The graph stores world models, coordinator knowledge, and patterns across sessions. |
| `scope` | global — the persistent memory substrate for all coordinators |
| `completion_criteria` | At least one coordinator can read from and propose writes to the graph through the promotion mechanism. World model data survives session boundaries. |
| `review_trigger` | After C-001 is fully complete and at least one coordinator has completed a live startup sequence |
| `blocking_proposals` | none |

---

### C-003 — Add TEACHING_MODE.md to GameAgentCore

| Field | Value |
|---|---|
| `id` | C-003 |
| `created` | 2026-05-18 |
| `owner` | game-agent-core |
| `status` | active |
| `description` | Define a structured protocol for game-learning sessions: how corrections get captured, how observations become proposals, how the agent behaves when learning vs. when it knows a game. Unblocks productive 觅长生 and other game sessions. |
| `scope` | game-agent-core — applies to all game agent workspaces |
| `completion_criteria` | TEACHING_MODE.md exists in GameAgentCore. At least one game session uses it to generate at least one valid proposal. |
| `review_trigger` | Next active game agent session |
| `blocking_proposals` | none |

---

### C-004 — Build Discord coordinator bot ecosystem

| Field | Value |
|---|---|
| `id` | C-004 |
| `created` | 2026-05-18 |
| `owner` | gopher-workbench-mcp |
| `status` | blocked |
| `description` | Build Claude API-powered and Codex-powered Discord bots for coordinator roles. Each coordinator gets a dedicated Discord channel. Absorbs Vaultbot into the Memory coordinator when Memory is operational. Named by function/purpose (Memory, Reason, Hands, etc.). |
| `scope` | global — Discord interface layer for the whole system |
| `completion_criteria` | At least one non-Vaultbot coordinator bot is operational, completing Article IX startup and processing at least one request. |
| `review_trigger` | After C-001 is complete and governance foundation is stable |
| `blocking_proposals` | none |

---

## Closed Commitments

*(none yet)*

---

## Paused / Superseded

*(none yet)*

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
