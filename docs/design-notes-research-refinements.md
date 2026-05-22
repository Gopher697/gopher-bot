# Proposal: P-001 — Research-Sourced Design Refinements

| Field | Value |
|---|---|
| `id` | P-001 |
| `created_at` | 2026-05-19T00:00:00Z |
| `proposed_by` | Claude (Gopher-bot Expert session) |
| `target_layer` | `world_model` |
| `target_environment` | `global` |
| `proposed_claim` | Five architectural refinements identified from a survey of current research (EpisTwin, RUVA, MemMachine, Memoria, Microsoft sovereignty kernel, PersonalAI benchmarks) that improve the graph schema, audit integrity, and audit panel without requiring redesign of any existing coordinator. |
| `evidence` | Research survey conducted 2026-05-19. Relevant papers: EpisTwin (arxiv 2603.06290), RUVA (arxiv 2602.15553), MemMachine (arxiv 2604.04853), Memoria (arxiv 2512.12686), Right to History sovereignty kernel (arxiv 2602.20214), PersonalAI retrieval benchmarks (arxiv 2506.17001). |
| `prediction_made` | None yet — these are prospective design improvements, not corrections to observed failures. |
| `falsification_condition` | Any refinement here that conflicts with existing coordinator behavior or graph schema should be flagged and not implemented until the conflict is resolved. |
| `scope_limits` | All five items are additive. None require modifying existing coordinators or breaking the current graph schema. Item 5 is a testing methodology, not a code change. |
| `risk_level` | low |
| `destination_path` | Multiple: graph schema, logging module, audit panel (future), testing protocol |
| `human_decision` | pending |
| `decision_timestamp` | — |
| `decided_by` | — |
| `decision_source` | — |
| `decision_statement` | — |
| `notes` | Gopher reviewed and approved adding these to the proposal queue on 2026-05-19. He is not asking for a major redesign — these are refinements to implement opportunistically as each relevant component is built or tested. Priority order suggested below. |

---

## The Five Refinements

### Refinement 1 — Observation/Inference Separation in Graph Schema
**Source:** MemMachine (ground-truth-preserving architecture)
**Priority: HIGH — implement before the graph has real data**

Currently all graph nodes (Observation, etc.) look the same regardless of whether they represent something directly observed vs. something inferred from multiple observations. Once real data is in the graph, retrofitting this is painful.

**What to add:** A `source_type` property on Observation nodes:
- `observed` — directly stated by Gopher or directly witnessed by a coordinator
- `inferred` — derived from two or more observations by a coordinator
- `proposed` — submitted via the proposal mechanism, not yet confirmed by prediction success

Memory coordinator should tag every node it creates with the correct source_type. Pattern Monitor and Reason should treat `inferred` nodes with lower default confidence than `observed` nodes. The predict→act→compare→revise loop should be able to promote `inferred` to `observed` when the inference predicts correctly.

**Where to implement:** `world_models/` graph schema + `coordinators/memory.py` store() method.

---

### Refinement 2 — Confidence Weights and Decay on Graph Nodes
**Source:** Memoria (weighted knowledge graph user modeling)
**Priority: MEDIUM — implement when Memory coordinator is extended**

Currently an observation from three years ago has the same weight as one from yesterday. Stale unconfirmed nodes should lose confidence over time, without being deleted.

**What to add:** Two properties on Observation nodes:
- `confidence` — float 0.0–1.0, starts at 1.0 for observed, 0.7 for inferred
- `last_confirmed_at` — ISO datetime, updated when a node's claim predicts correctly

A background task (Dream coordinator is a natural home — it runs during idle) periodically applies decay: confidence drops by a small factor for nodes not confirmed in N days. Nodes below a threshold (e.g. 0.2) are flagged for review, not deleted. Pattern Monitor watches for clusters of decaying nodes as a signal of a changing pattern.

**Where to implement:** `world_models/` schema + Dream coordinator background_tick() + Pattern Monitor.

---

### Refinement 3 — Hash-Chained Audit Logs
**Source:** Right to History sovereignty kernel (Merkle tree audit logs)
**Priority: MEDIUM — implement when audit logging is formalized**

The charter requires append-only audit logs but currently enforces this only by convention. A `prev_hash` field on each log entry makes tampering structurally detectable without enterprise complexity.

**What to add:** Each log entry in `logs/build/YYYYMMDD.md` and `logs/actions/YYYYMMDD.md` includes:
- `prev_hash` — SHA-256 of the previous entry's full text (or `genesis` for first entry of the day)

A simple verification script (`scripts/verify_logs.py`) can walk the chain and flag any entry whose prev_hash doesn't match. This doesn't prevent a determined attacker but makes accidental or casual tampering immediately visible — consistent with the charter's audit spirit.

**Where to implement:** Logging utility (new: `utils/audit_log.py`) + `scripts/verify_logs.py`.

---

### Refinement 4 — Plain-Language Graph Inspection + Targeted Redaction (Audit Panel Feature)
**Source:** RUVA ("glass box" human-in-the-loop memory curation)
**Priority: LOW — audit panel is a later phase**

Currently deleting a specific fact from the graph requires going into Neo4j directly. The audit panel (planned) should include a "what does Gopher-bot know about me?" view that presents graph contents in plain language and allows precise deletion of specific nodes.

**What to add to the audit panel:**
- A `Memory Inspector` tab that queries the graph and renders each Observation node as a plain-language sentence (Voice coordinator can synthesize these)
- A `Delete this fact` button per node that submits a deletion proposal through the normal mechanism (not a direct write)
- Filter by source_type (observed / inferred / proposed) and confidence level

**Where to implement:** `interface/` audit panel UI — when audit panel is built (post-Hands phase).

---

### Refinement 5 — Benchmarked Retrieval Comparison Before Optimizing Memory
**Source:** PersonalAI paper (systematic knowledge graph retrieval comparison)
**Priority: LOW — testing methodology, not a code change**

Before optimizing Memory coordinator's retrieval logic, run the current hybrid approach (vector similarity + keyword fallback) against the PersonalAI benchmark methodology. Their paper found meaningful differences between retrieval strategies that weren't obvious without systematic comparison.

**What to do:** When writing tests for Memory coordinator retrieval, structure them so they can be run comparatively against alternative strategies (pure vector, pure keyword, hybrid, graph traversal). Don't assume the current approach is optimal — measure it first.

**Where to implement:** `tests/test_memory_retrieval.py` — add comparative benchmark harness.
Reference: https://arxiv.org/pdf/2506.17001

---

## Suggested Implementation Timing

| Refinement | When to implement |
|---|---|
| 1 — source_type on graph nodes | Before any real data enters the graph — do this SOON |
| 2 — confidence weights + decay | When extending Memory coordinator or building Dream |
| 3 — hash-chained logs | When formalizing the logging utility |
| 4 — glass box audit panel | When building the audit panel (post-Hands phase) |
| 5 — retrieval benchmarks | When writing Memory coordinator tests |
