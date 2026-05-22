# Agent Commitments

**Governed by:** Persistent Agent Charter (`AGENT_CHARTER.md`) Article VI
**Last updated:** 2026-05-20 (C-004 closed; C-006 closed — all inner defender criteria met)
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
| `owner` | gopher-workbench |
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
| `owner` | gopher-workbench |
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
| `owner` | gopher-workbench |
| `status` | closed |
| `closed` | 2026-05-20 |
| `description` | Build the full coordinator architecture on a self-hosted web interface (not Discord — privacy decision made 2026-05-18). Includes: async bid-gating Awareness hub, background brain loop running coordinators on independent cadences, all planned coordinators implemented as async workers, web UI for Chad interaction (voice + text), and audit panel for coordinator activity. Absorbs Vaultbot into Memory when Memory is operational. |
| `scope` | global — interface and coordinator execution layer for the whole system |
| `completion_criteria` | Background brain loop running alongside Flask. At least three background coordinators (Feeling, Pattern Monitor, Curiosity) submitting bids to Awareness independently of Chad input. Voice responding both reactively (to Chad messages) and proactively (from coordinator bids). Audit panel shows live coordinator activity. |
| `review_trigger` | After first proactive Voice output surfaces from background brain without Chad prompt |
| `blocking_proposals` | none |

---

### C-005 — Interface architecture: phased ambient OS presence

| Field | Value |
|---|---|
| `id` | C-005 |
| `created` | 2026-05-19 |
| `owner` | gopher-workbench |
| `status` | active |
| `description` | Build the interface layer in three phases toward a purpose-built AI-native execution environment. Phase 1 (done): Flask + SocketIO web app with voice and text, BrainLoop daemon thread, static frontend. Phase 2: Tauri desktop wrapper giving Gopher-bot OS-level ambient awareness — Sensory receives passive screen/file/app context without explicit Chad input; Hands and Sensory designed for system-level access from day one. Phase 3 (the dream): NixOS-based custom Linux environment where coordinators are first-class system services with MAC enforcement (AppArmor/SELinux), the knowledge graph is the persistence primitive, build/runtime separation is a kernel-level privilege boundary, and the interface is a spatial navigator through the knowledge graph rather than a chat window. |
| `scope` | global — interface and execution environment for the whole system |
| `completion_criteria` | Phase 1: Flask server running with BrainLoop, voice + text endpoints live (done). Phase 2: Tauri app wrapping Flask; Sensory receiving passive OS-level context; Hands built with policy interception designed for system-scope. Phase 3: NixOS distro config committing coordinator services, MAC profiles, and graph-as-persistence layout. |
| `review_trigger` | When Hands coordinator (Task 29) is being designed — must account for Phase 2 system-level access patterns before implementation. |
| `blocking_proposals` | none |

---

### C-006 — Temporal self-awareness and inner defense

| Field | Value |
|---|---|
| `id` | C-006 |
| `created` | 2026-05-20 |
| `owner` | gopher-workbench |
| `status` | closed |
| `closed` | 2026-05-20 |
| `description` | Build the temporal self-awareness layer and close the inner defense loop. Two inseparable components: (1) **Temporal layer** — all coordinators gain access to real-world time via shared utils; BrainLoop packets carry current_time, session_age, time_since_last_nrem, and time_since_last_gopher_input; graph is queryable by time range; Dream has circadian NREM scheduling; audit log can answer "time since last action of type X." (2) **Inner defense** — Dream AUDIT runs verify_chain() autonomously during NREM and spikes NE + writes DreamLog alert on chain failure; Pattern Monitor detects coordinator behavioral drift vs. established baseline; Mirror-Self flags Reason outputs that deviate from the self-model; OpenTimestamps anchors the audit log chain head to Bitcoin nightly, grounding the AI's action timeline in external tamper-evident time. The inner defender has alerting authority only — no action authority. Without this commitment, trust escalation (Task 49) and autonomous idle operation (Task 48) cannot be safely designed. |
| `scope` | global — temporal context affects all coordinators; inner defense is the prerequisite for unsupervised autonomous operation |
| `completion_criteria` | (1) BrainLoop packets carry timestamp, session_age_seconds, time_since_last_nrem, time_since_last_interaction. (2) Dream AUDIT runs verify_chain() every NREM cycle and logs result to DreamLog. (3) OpenTimestamps .ots proof file written to logs/audit/timestamps/ nightly. (4) Pattern Monitor behavioral baseline active; drift >2σ submits high-priority bid to Awareness. (5) Mirror-Self self-model deviation logging active. |
| `review_trigger` | Before trust escalation protocol (Task 49) is designed — trust requires a verified temporal track record the AI can read and reason over |
| `blocking_proposals` | none |

---

## Closed Commitments

C-004 — closed 2026-05-20. All three completion criteria met: Pattern Monitor coordinator
ticking at 90s cadence and submitting bids (commit 833708e); audit panel live at /audit
with neuromodulator display and coordinator activity feed (commit 9adbe62); proactive
Voice output from BrainLoop on high-priority bids, rate-limited 60s, first message
verified in browser (this commit).

C-006 — closed 2026-05-20. All five completion criteria met: BrainLoop packets carry
temporal fields including time_since_last_interaction (Task 59, commit recorded);
Dream AUDIT runs verify_chain() autonomously each NREM cycle with DreamLog output
(Task 47); OpenTimestamps .ots proofs written to logs/audit/timestamps/ nightly (Task 61,
commit ba14030); Pattern Monitor baseline active with >2σ drift detection (Task 56);
Mirror-Self self-model deviation logging active (Tasks 26, 60). Inner defender loop closed.
Trust escalation protocol (Task 49) now unblocked.

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
