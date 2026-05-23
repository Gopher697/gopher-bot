# Gopher-bot Research Findings

Running log of design ideas and documented failure modes from the academic literature.
Maintained by Claude (Director) sessions. Use this as context before deep-dive research runs.

**Last updated:** 2026-05-19 (Session: Gopher-bot Expert — Rounds 2 + 3 + interface architecture appended)

---

## Papers Surveyed

| Paper | arXiv | Key theme |
|---|---|---|
| EpisTwin | 2603.06290 | PKG + neuro-symbolic personal AI, community detection |
| PersonalAI | 2506.17001 | KG storage/retrieval comparison, 6 retrieval methods |
| PersonalAI 2.0 | 2605.13481 | Planning mechanism for KG traversal |
| Anatomy of Agentic Memory | 2602.19320 | Memory taxonomy, backbone-dependency failure mode |
| Theater of Mind | 2604.08206 | GWT implementation for LLMs, stagnation failure mode |
| MemMachine | 2604.04853 | Ground-truth episode storage, error compounding |
| Memory as Metabolism | 2604.12034 | TRIAGE→CONSOLIDATE→AUDIT loop, entrenchment |
| RUVA | 2602.15553 | On-device graph reasoning, vector ghost deletion |
| Why Do Multi-Agent LLM Systems Fail? (MASFT) | 2503.13657 | 14 failure modes taxonomy across 5 MAS frameworks |
| SCM (Sleep-Consolidated Memory) | 2604.20943 | 5-phase sleep-inspired memory; NREM + REM + intentional forgetting |
| D-MEM (Dopamine-Gated Memory) | 2603.14597 | RPE-based fast/slow routing; Critic Router; 80% token reduction |
| Persistent Identity (soul.py) | 2604.09588 | Multi-anchor identity; 6 separable components; drift detection via Hamming hash |
| ZenBrain | 2604.23878 | 7-layer memory + 15-algorithm ablation; 4-channel NeuromodulatorEngine; Two-Factor KG edges |
| Fault-Tolerant Sandboxing | 2512.12806 | Policy interception + transactional filesystem snapshots; 100% high-risk intercept rate |
| Temporal Affective Pattern Recognition | 2601.12341 | Time-continuous affective trajectory modeling for multi-turn longitudinal interactions |

---

## Design Ideas Worth Stealing

### 1. TRIAGE → CONSOLIDATE → AUDIT loop *(Memory as Metabolism, 2604.12034)*
**Mapped to:** Task 27 (Dream coordinator — scope now expanded)

The paper introduces "memory gravity": beliefs that are well-established in the graph resist correction. Dominant interpretations accumulate structural weight and incoming evidence is assimilated rather than evaluated. 

**The fix:** TRIAGE incoming observations (score against existing high-gravity nodes, reject obvious noise, defer coherence decisions to the scheduled loop). CONSOLIDATE in scheduled Dream sessions (merge supporting evidence, update confidence weights, allow accumulated minority-position evidence to challenge dominant beliefs). AUDIT periodically for entrenchment — beliefs that have gone unchallenged too long, especially those tightly coupled to the user's expressed views.

**Why it matters for Gopher-bot:** Without the AUDIT step, a single-user companion system drifts toward becoming a mirror. Over thousands of interactions it stops having independent views and reflects Gopher back at himself. Mirror-Self is the coordinator most vulnerable to this; Dream is the natural enforcement point.

---

### 2. Raw episode storage + contextualized retrieval *(MemMachine, 2604.04853)*
**Mapped to:** Task 42 (new)

Every time Memory extracts a fact from conversation using an LLM call, there is inference noise. Over thousands of graph writes, these errors compound. MemMachine's fix: store the raw conversational episode as a ground-truth node alongside the extracted triples. When retrieval hits a nucleus match, expand to include surrounding episode context (1-2 turns before/after).

**Why it matters for Gopher-bot:** Memory currently extracts facts and discards the raw source. The graph is drifting from ground truth from day one. Episode nodes also solve MASFT FM-1.4 (loss of conversation history) — the synchronous pipeline has no persistent cross-message thread.

---

### 3. Community detection for latent associations *(EpisTwin, 2603.06290)*
**Mapped to:** Future graph work (no current task — post-coordinator phase)

Leiden algorithm used to find clusters of nodes that are semantically cohesive but not explicitly connected by triples. Example: an Event node and its reminder Alarm node that share contextual meaning but no explicit edge. Community detection finds these latent groupings and reifies them as new Community entities in the graph, connected to all member nodes.

**Concrete use for Gopher-bot:** The knowledge graph will accumulate thousands of Observation nodes. Community detection can surface thematic clusters that no single coordinator would notice: e.g., a cluster of anxious observations around a specific life domain that Feeling has tagged, or a cluster of curiosity gaps all orbiting the same unknown concept.

**Note:** EpisTwin's own limitations section flags scalability: community detection degrades as the graph grows. Need pruning/archiving strategy before this becomes viable.

---

### 4. Confidence threshold-gating for bids *(MASFT, 2503.13657)*
**Mapped to:** Awareness coordinator implementation

The paper proposes agents should act only when their confidence exceeds a defined threshold; when confidence is low, they should pause to gather information rather than proceed. Suggests adaptive thresholding (dynamically adjusted based on context).

**For Gopher-bot:** Awareness currently gates bids by priority. Adding a confidence field to the Bid object and requiring coordinators to declare confidence would let Awareness filter out low-confidence bids in high-stakes moments without rejecting them permanently (they can be re-submitted with more evidence).

---

### 5. Event-driven dynamical system over passive message passing *(Theater of Mind, 2604.08206)*
**Mapped to:** Confirms current architecture — no action needed

Paper independently derives Global Workspace Theory as the solution to multi-agent cognitive stagnation. Systems using static memory pools + passive message passing hit homogeneous deadlocks during extended execution. Event-driven architectures with active coordinator agents avoid this.

**Status for Gopher-bot:** This is exactly what the async bid-gating brain loop is. Confirmation the architecture choice was correct. Warning: do not let Awareness become a passive router. It must remain an active gating process — "decide and hold" not "forward everything."

---

### 6. Sleep-phase memory consolidation — NREM + REM + forgetting *(SCM, 2604.20943)*
**Mapped to:** Task 27 (Dream coordinator — now has explicit phase model)

The paper implements a 5-component sleep-inspired memory cycle:
1. **Working memory** — recent observations held in fast buffer
2. **Importance tagging** — salience scoring before consolidation
3. **NREM consolidation** — Hebbian strengthening of co-occurring patterns + synaptic downscaling (reduces noise, strengthens signal). 90.9% noise reduction.
4. **REM dreaming** — novel association generation by replaying memories in novel combinations. Finds latent connections working memory never would.
5. **Intentional forgetting** — value-based deletion: low-importance + low-confidence + low-recency nodes are pruned, not just decayed.

Results: perfect recall on benchmarks where standard retrieval fails; 90.9% noise reduction.

**For Gopher-bot:** Dream's TRIAGE→CONSOLIDATE→AUDIT maps almost directly to Working Memory→NREM→REM. The SCM paper gives us the explicit algorithm for each phase. Specific additions:
- NREM phase: strengthen edges between co-occurring Observation nodes; apply downscaling pass to reduce weak co-occurrence noise
- REM phase: novel association generation — inject two randomly selected high-salience community clusters and ask LLM to find connections neither coordinator has noticed
- Intentional forgetting: operate on a scored deletion queue (confidence × recency × importance), not arbitrary decay

**New task generated:** Task 44 — SCM-informed Dream phases (add explicit NREM pass + REM novel-association pass + scored deletion queue to Dream coordinator spec)

---

### 7. RPE-based fast/slow memory routing *(D-MEM, 2603.14597)*
**Mapped to:** Task 28 (Neuromodulation infrastructure)

D-MEM introduces a **Critic Router** that computes Reward Prediction Error (RPE = Surprise + Utility) for every incoming input:
- **Low RPE** (routine, expected input) → O(1) fast buffer, no full memory pipeline. 80%+ token reduction on routine conversations.
- **High RPE** (contradictions, unexpected facts, preference reversals, novel strong emotional events) → "dopamine" signal triggers full O(N) memory evolution: episodic encoding + graph update + consolidation scheduling.

The Critic Router evaluates two signals:
- **Surprise**: how much does this contradict or extend existing graph beliefs?
- **Utility**: how useful is this for future decision-making?

**For Gopher-bot:** This is exactly what Neuromodulation (Task 28) needs. The SystemState graph node should track a `dopamine` field (current RPE signal strength). Awareness can query SystemState.dopamine before routing — high dopamine → all background coordinators wake for a tick, low dopamine → only Feeling and Mirror-User tick (resource conservation). The D-MEM Critic Router logic (Surprise + Utility) becomes the core of Neuromodulation's `assess_salience()` method.

**New task generated:** Task 45 — D-MEM Critic Router in Neuromodulation (implement RPE = Surprise + Utility scoring in Neuromodulation coordinator; SystemState.dopamine drives tick frequency)

---

### 8. Multi-anchor distributed identity *(Persistent Identity, 2604.09588)*
**Mapped to:** Task 26 (Mirror-Self) + future SOUL.md/SALIENCE.md work

The paper (soul.py) demonstrates that AI systems lose coherent identity when relying on a single memory store, because memory damage causes cascade failure. Humans survive amnesia because identity is distributed across separable systems. Their solution: 6 separable identity anchors:

1. **SOUL.md** — core values, beliefs, fundamental character (rarely updated, high-confidence only)
2. **MEMORY.md** — episodic and semantic memory (frequently updated)
3. **PROCEDURES.md** — learned behavioral patterns and skills
4. **SALIENCE.md** — what the system currently finds important (dynamic)
5. **RELATIONS.md** — social graph and relationship history
6. **IDENTITY_HASH.md** — Hamming distance hash of canonical probe responses (drift detection)

**Identity Drift Detection:** A set of canonical probe questions is embedded at a fixed context size. After every N sessions, responses are re-run and compared to baseline via Hamming distance. Distance > threshold → identity drift alert. This is quantitative, not subjective.

**Hybrid RAG+RLM retrieval:** 90% of queries (focused) → fast vector RAG. 10% of queries (existential, relationship, deep relational) → recursive LLM synthesis across all anchors.

**Lamarckian inheritance:** Learned behaviors can be explicitly serialized into PROCEDURES.md and passed to a reinitialized instance — AI evolution without biological constraint.

**For Gopher-bot:** Mirror-Self's state file (mirror_self_state.json) is a weak single-anchor. Full implementation should:
- Add `SOUL.md` to the repo as Gopher-bot's stable identity anchor (values, not personality)
- Mirror-Self maintains a `self_probe_responses.json` baseline and runs drift checks via Hamming distance every 50 sessions
- SALIENCE.md equivalent: a dynamic "what Gopher-bot finds salient right now" node in the graph (Pattern Monitor feeds this)
- RELATIONS.md equivalent: already partially covered by Mirror-User's user model; needs formal relation nodes in the graph
- Hybrid retrieval routing: Memory coordinator should split queries — short focused queries → vector, long relational queries → full graph traversal

**New tasks generated:** 
- Task 46 — Mirror-Self drift detection (canonical probe set + Hamming hash comparison, runs every 50 sessions via Dream)
- Task 47 — Hybrid retrieval routing in Memory (query classifier: focused → vector RAG, relational → WaterCircles traversal)

---

### 9. ZenBrain 4-channel NeuromodulatorEngine *(ZenBrain, 2604.23878)*
**Mapped to:** Task 28 (Neuromodulation infrastructure) — replaces the weaker D-MEM-only spec

ZenBrain is the most complete neuroscience-grounded AI memory system found in the literature. Its **NeuromodulatorEngine** implements all four major neuromodulators as first-class runtime parameters:

| Channel | Brain region | Output parameter |
|---|---|---|
| Dopamine (DA) | VTA | learning-rate |
| Norepinephrine (NE) | Locus Coeruleus | exploration-bias |
| Serotonin (5HT) | Raphe nuclei | consolidation-patience |
| Acetylcholine (ACh) | Basal Forebrain | attention |

Mechanism: each channel maintains a tonic baseline with 5-minute half-life phasic bursts. DA/5HT opposition coupling: when dopamine spikes (novelty/reward), serotonin suppresses; when serotonin is high (stability/routine), dopamine activity is dampened. The four output parameters are consumed by downstream engines (Dream/Memory/Awareness).

Also critical: **PriorityMap** formula P = w_s·s + w_e·|v| + w_r·r + w_g·g (saliency/emotion/reward/goal). Amygdala fast-path: if |v| > 0.6 (high emotional valence) → P ≥ 0.5 regardless of other weights. Weights dynamically rescaled by neuromodulator state.

**For Gopher-bot Neuromodulation (Task 28):**
- SystemState graph node: add `dopamine`, `norepinephrine`, `serotonin`, `acetylcholine` float fields with tonic baselines
- Neuromodulation coordinator's `background_tick()` decays phasic bursts (5-min half-life) and resets toward tonic
- When Awareness receives a bid, it reads SystemState neuromodulators to determine: how deep to run memory pipeline (ACh = attention weight), how long Dream should consolidate (5HT = patience), whether to accept exploratory Curiosity bids (NE = exploration-bias), how much to weight novel observations (DA = learning-rate)
- Amygdala fast-path: if Feeling reports |valence| > 0.6 → Awareness immediately admits bid regardless of priority queue position (DA phasic burst triggers)

**New task generated:** Task 48 — Implement PriorityMap formula in Awareness bid-gating (P = weighted saliency + emotional valence + recency + goal-alignment; amygdala fast-path for high-valence bids)

---

### 10. Two-Factor Synaptic Model for KG edges *(ZenBrain, 2604.23878)*
**Mapped to:** Task 40 (confidence weight + decay) — replaces vague decay spec

Each KG edge carries TWO fields (not one):
1. **Weight w_ij** — the current strength of the relationship (0.0 to 1.0)
2. **Consolidation variance σ²_ij** — the Fisher Information proxy: I_ij = 1/σ²_ij. As an edge accumulates co-occurrence evidence, variance decreases, Fisher Information increases, and the edge becomes resistant to overwriting.

Rule: changes to an edge are penalized in proportion to I_ij. New evidence arriving for a well-consolidated edge must be very strong (high PE/RPE) to shift it. This implements the StabilityProtector rule from ZenBrain: only PE > 0.5 + 0.3·L·ρ may overwrite (where L = lock score derived from Fisher Information, ρ = rigidity factor).

This directly mitigates FM-B (memory entrenchment) in a mathematically principled way: it is harder to overwrite high-confidence beliefs, but not impossible. The threshold scales continuously with evidence.

**For Gopher-bot graph schema:** Replace the single `confidence` field on edges with `weight` + `consolidation_variance`. Dream's NREM pass updates both fields: co-occurring edges gain weight and lose variance; non-co-occurring edges lose weight and gain variance (downscaling).

---

### 11. Simulation-Selection Sleep loop (CA3/CA1 RL) *(ZenBrain, 2604.23878)*
**Mapped to:** Task 27 (Dream coordinator — NREM phase algorithm)

ZenBrain's Simulation-Selection Sleep Loop is the most rigorous implementation of NREM consolidation found. Two-stage RL loop:
1. **CA3 Simulator**: Assembles replay candidates from: (a) real recorded episodes AND (b) counterfactual combinations — pairs of episodes that share no direct edge but might yield useful associations
2. **CA1 Selector**: Scores each candidate via TAG(e) = α|δ_TD| + βR_e + γN_e (temporal-difference error + reward + novelty). High-TAG episodes get LTP (strengthened); low-TAG get LTD (weakened/pruned).

Result: 37% stability improvement with 47.4% storage reduction through RL-driven replay selection (vs heuristic replay in all other systems surveyed).

**For Gopher-bot Dream:**
- CA3 phase: collect episodes from ConversationEpisode nodes (Task 42) + generate counterfactual pairs by sampling high-salience nodes from different clusters
- CA1 phase: score each via TAG(e) — temporal-difference (did this turn out as predicted?), reward (did Gopher express satisfaction?), novelty (how much did this observation update existing beliefs?)
- High-TAG: update edge weight + reduce variance. Low-TAG below threshold: add to deletion queue (scored deletion from SCM)

---

### 12. MetacognitiveMonitor for Dream AUDIT *(ZenBrain, 2604.23878)*
**Mapped to:** Task 27 (Dream coordinator — AUDIT phase)

ZenBrain's MetacognitiveMonitor tracks three bias types continuously:
1. **Confirmation bias**: Measures ratio of confirming vs. disconfirming evidence for high-weight beliefs. When confirmation ratio exceeds threshold → bias alert.
2. **Recency bias**: Detects when recent observations are weighted disproportionately vs. historical evidence. Triggers when recent-vs-historical ratio exceeds threshold.
3. **Retrieval efficiency**: Tracks query precision-recall trends. Degrading efficiency → memory structure alert.

After high-PE events (PE > 0.7), the monitor opens a 10-minute novelty window: incoming observations during this window get elevated learning-rate, allowing rapid belief updating. Outside the window, conservative consolidation-patience applies.

**For Gopher-bot Dream AUDIT phase:**
- After TRIAGE → CONSOLIDATE, Dream runs MetacognitiveMonitor checks
- Confirmation bias check: count confirming vs. disconfirming evidence for top-N high-confidence graph nodes; if ratio > threshold → flag for Gopher via DreamLog entry (not auto-correct)
- Recency bias check: compare last-30-day observation distribution vs. 90-day baseline; large divergence → entrenchment alert
- High-PE novelty window: after any Feeling observation with |valence| > 0.7, Dream schedules a fast mini-consolidation pass instead of waiting for full idle threshold

---

### 13. Policy-based interception + transactional rollback for safe tool execution *(Fault-Tolerant Sandboxing, 2512.12806)*
**Mapped to:** Task 29 (Hands coordinator)

The paper wraps agent actions in atomic transactions with two safety layers:
1. **Policy-based interception layer**: Before any command executes, a policy engine classifies the command against a risk taxonomy. High-risk commands (rm -rf, network writes, credential access, process spawning outside whitelist) are intercepted and require explicit approval or are blocked outright. Result: 100% interception rate for high-risk commands.
2. **Transactional filesystem snapshot mechanism**: Before each file-modifying action, the current filesystem state is snapshotted. If the action produces an error or returns a failed state, the snapshot is restored. Result: 100% rollback success rate.

The paper explicitly notes that commercial solutions (container sandboxes, interactive CLIs) add too much latency or break headless loops. The transactional approach adds only snapshot overhead, not container initialization.

**For Gopher-bot Hands coordinator:**
- All Hands actions must run through a pre-execution policy check: classify action → whitelist/greylist/blacklist
- Whitelist: file reads, web searches, subprocess calls against a known-safe command list
- Greylist: file writes, subprocess calls with arguments, API calls (require Awareness approval / priority gate before executing)
- Blacklist: rm -rf, network write outside known endpoints, credential file access, anything touching world_models/config.py
- After every whitelist/greylist action: snapshot the affected file(s) to a rollback buffer. On error: restore from snapshot, log to logs/actions/, submit error bid to Awareness
- Tier assignment: whitelist → Tier 1 can execute; greylist → Tier 2 approval required; blacklist → requires Gopher's live session approval via charter proposal mechanism

---

### 14. Temporal affective trajectory modeling for Pattern Monitor *(Temporal Affective, 2601.12341)*
**Mapped to:** Task pending (Pattern Monitor coordinator)

The paper introduces time-continuous affective trajectory modeling — instead of classifying each message's emotion discretely (happy/sad/neutral), it fits a continuous trajectory function over a conversation or session window. Key insight: the *slope* and *curvature* of the affective trajectory are more informative than any single point.

Applied findings for Pattern Monitor:
- Track affect trajectory slope over sessions: consistently rising → positive engagement trend; consistently declining → needs attention even if any single session was rated neutral
- Physics-informed NN as model type: uses differential equations to model trajectory continuity rather than discrete state transitions — trajectories can't jump discontinuously
- Temporal patterns across domains: some topics consistently produce rising trajectories (curiosity, energy), others produce declining ones (frustration, avoidance)

**For Gopher-bot Pattern Monitor:**
- Pattern Monitor does not just snapshot "Gopher felt anxious today" — it tracks the *trajectory* of affective states across topics over N sessions
- Pattern signature: a cluster of observations tagged with [topic, valence, session_timestamp] forms a trajectory point series; Pattern Monitor fits a trend line and stores the slope + curvature as graph properties of the relevant Topic node
- Threshold: slope below −0.1 per session for a topic with >5 data points → submit bid to Awareness (topic-decline pattern detected)
- Positive patterns are also worth bidding: topic with rising trajectory + high curiosity tag → Curiosity coordinator gets a relevance boost signal for that topic

---

### 15. Multiple retrieval strategies *(PersonalAI, 2506.17001)*
**Mapped to:** Future Memory enhancement (post-coordinator phase)

Benchmarks six retrieval methods: A*, WaterCircles traversal, beam search, and hybrid methods. Finding: no single retrieval method dominates across all query types. Hybrid (semantic vector + graph traversal) outperforms pure-vector and pure-graph approaches. The WaterCircles method (concentric ring expansion from nucleus match outward) is particularly effective for personal knowledge queries.

**For Gopher-bot:** Memory currently uses semantic vector search with keyword fallback. WaterCircles traversal should be explored as a third retrieval mode for relational queries ("what do I know about X's relationship to Y?").

---

## Documented Failure Modes from the Field

### FM-A: LLM extraction error compounding *(MemMachine, 2604.04853)*
**Severity for Gopher-bot:** HIGH

Every graph write made via LLM inference introduces small errors. Over thousands of writes, the graph drifts from the actual truth of conversations. No current mitigation in Gopher-bot.

**Mitigation:** Task 42 (raw episode nodes). Task 39 (source_type field — lets the system distinguish `observed` from `inferred` and weight accordingly).

---

### FM-B: User-coupled drift / memory entrenchment *(Memory as Metabolism, 2604.12034)*
**Severity for Gopher-bot:** HIGH (unique to single-user companion systems)

A companion system trained exclusively on one person's data will gradually mirror that person's worldview. The system stops offering independent perspective and becomes an echo chamber. "Memory gravity" makes established beliefs structurally resistant to correction.

**Mitigation:** Task 27 (Dream AUDIT step). Mirror-Self needs explicit anti-entrenchment logic: track when its own model hasn't updated on a topic for N sessions despite new incoming data. This is a sign of entrenchment, not stability.

---

### FM-C: Vector ghost deletions *(RUVA, 2602.15553)*
**Severity for Gopher-bot:** MEDIUM

Deleting a Neo4j node does not remove its nomic-embed vector index entry. The embedding persists and can still be retrieved semantically, violating user-directed forgetting and producing stale retrieval.

**Mitigation:** Task 43 (vector deletion cascade).

---

### FM-D: Loss of conversation history *(MASFT FM-1.4)*
**Severity for Gopher-bot:** MEDIUM

Synchronous pipeline has no persistent cross-message thread node. Memory retrieves facts but cannot reconstruct the arc of a conversation. Between sessions, the context of *how* something was said is lost even if the fact was extracted.

**Mitigation:** Task 42 (ConversationEpisode nodes).

---

### FM-E: Role specification violation *(MASFT FM-1.2)*
**Severity for Gopher-bot:** MEDIUM (already partially mitigated)

BUG-001 fixed the build/runtime version. Runtime risk remains: coordinators overstepping into each other's domains. Specific risk: Voice deciding not to say something (timing judgment — Awareness's job), or Reason writing directly to graph (Memory's job), or Feeling submitting actions rather than signals.

**Mitigation:** Charter already governs this. Enforcement during coordinator implementation: each coordinator's `process()` and `background_tick()` must have clearly scoped write paths matching the registry.

---

### FM-F: Unaware of stopping conditions *(MASFT FM-1.5)*
**Severity for Gopher-bot:** MEDIUM

Background coordinators currently defined only by tick_interval. Without explicit documented stopping conditions, a misbehaving coordinator either silently disappears from the loop or runs indefinitely without progress.

**Mitigation:** Each coordinator's background_tick should return a status dict including a `health` field. BrainLoop already catches exceptions and stores `last_errors` — build on this: add a `max_consecutive_errors` threshold that triggers a coordinator to self-suspend and write a log entry.

---

### FM-G: Reasoning-action mismatch *(MASFT FM-2.6)*
**Severity for Gopher-bot:** MEDIUM

Voice generates language from Reason's output. If Voice receives a summarized or abbreviated version of Reason's structured output, the spoken response can diverge from what Reason actually determined. Reason says "this is uncertain, flag for clarification" and Voice says "here is a confident answer."

**Mitigation:** Voice must receive Reason's full structured output dict, not a text summary. The packet passing through the synchronous pipeline should be the authority — Voice reads `packet["reason_output"]` directly, not a re-summarization.

---

### FM-H: No verification step *(MASFT FM-3.2)*
**Severity for Gopher-bot:** LOW (for now)

Critic coordinator is planned but not built. Currently Awareness does the only filtering, and it gates by priority/timing, not by reasoning quality. A confident but wrong Reason output goes straight to Voice uncontested.

**Mitigation:** Critic coordinator (post-coordinator phase). In the meantime: Reason's prompting should include explicit uncertainty flagging, and Voice should be instructed to qualify uncertain responses.

---

### FM-I: Backbone model dependency *(Anatomy of Agentic Memory, 2602.19320)*
**Severity for Gopher-bot:** LOW (mitigated by tier routing)

Performance varies significantly depending on which backbone model handles a given inference. The three-tier routing partially mitigates this, but a weak tier-1 local model still produces weak graph writes regardless of tier.

**Mitigation:** Three-tier routing already in place. Additional mitigation: source_type field (Task 39) lets the system track which tier extracted an observation, making low-confidence tier-1 writes distinguishable from higher-confidence tier-2 writes.

---

### FM-K: Single-anchor identity fragility *(Persistent Identity, 2604.09588)*
**Severity for Gopher-bot:** HIGH (Mirror-Self is currently a single-anchor system)

mirror_self_state.json is the only persistent identity anchor. If this file is corrupted, overwritten by a bad Codex session, or drifts gradually from ground truth, there is no second anchor to detect or correct it. Gopher-bot could lose coherent self-model over time with no detection mechanism.

**Mitigation:** Task 46 (Mirror-Self drift detection — canonical probe baseline + Hamming hash). SOUL.md as a stable high-confidence anchor (only updated by explicit charter-governed proposal, never by background ticking). Dream coordinator runs drift check every 50 sessions during AUDIT phase.

---

### FM-L: Memory pipeline token overuse on routine inputs *(D-MEM, 2603.14597)*
**Severity for Gopher-bot:** MEDIUM (cost management concern, not a correctness failure)

The current synchronous pipeline runs full Memory.process() on every input regardless of novelty. Routine conversational inputs (greetings, acknowledgements, topic continuations) trigger the same graph lookup + LLM extraction pipeline as novel high-stakes inputs. Over thousands of sessions this becomes expensive without quality benefit.

**Mitigation:** Task 45 (D-MEM Critic Router in Neuromodulation). SystemState.dopamine field gates memory pipeline depth. Awareness checks dopamine level before deciding whether to call full Memory.process() or use cached context.

---

### FM-M: Memory noise accumulation without downscaling *(SCM, 2604.20943)*
**Severity for Gopher-bot:** MEDIUM (degrades over hundreds of sessions)

Without a periodic downscaling pass, weak co-occurrence edges accumulate in the graph. These are not wrong — they are statistically valid but low-signal. Over time they crowd out high-signal edges during retrieval. SCM demonstrates 90.9% noise reduction from NREM downscaling vs. no-downscaling baseline.

**Mitigation:** Task 44 (SCM-informed Dream phases — add explicit NREM downscaling pass to consolidation). Downscaling target: edges with strength < threshold that have not been reinforced in N sessions.

---

### FM-N: Unmonitored bias accumulation without MetacognitiveMonitor *(ZenBrain, 2604.23878)*
**Severity for Gopher-bot:** HIGH (confirmation bias is the second major single-user companion risk after entrenchment)

Without an active bias monitor, the graph will accumulate confirmation bias silently. High-confidence nodes attract confirming evidence (it's easier to update an existing belief than create a new one), and the ratio of confirming to disconfirming observations will diverge over time. The system will appear to learn faster but actually be narrowing. This is distinct from FM-B (entrenchment): entrenchment is about individual beliefs resisting change; FM-N is about the network systematically filtering out disconfirming observations at intake.

**Mitigation:** Task 27 (Dream AUDIT phase — MetacognitiveMonitor checks). Confirmation bias threshold + recency bias threshold should be tuned during testing. DreamLog entries should surface alerts to Gopher without auto-correcting.

---

### FM-O: Unguarded agent tool execution *(Fault-Tolerant Sandboxing, 2512.12806)*
**Severity for Gopher-bot:** HIGH (Hands coordinator is the highest-risk component in the system)

Hands is the only coordinator that can make irreversible real-world changes. Without a policy interception layer, a misbehaving Tier 1 LLM could execute high-risk commands (file deletions, network writes, credential access). An error in a Tier 1 model with no rollback mechanism could corrupt world_models/ or the Neo4j database with no recovery path. The paper demonstrates 100% interception of high-risk commands is achievable without container overhead.

**Mitigation:** Task 29 (Hands coordinator must include policy interception layer and transactional snapshot rollback as non-negotiable requirements). Charter Article VI: any Hands action that modifies files outside designated output directories must be logged to logs/actions/. world_models/config.py is blacklist.

---

### FM-J: Scalability cliff for community detection and multi-stage retrieval *(EpisTwin, 2603.06290)*
**Severity for Gopher-bot:** LOW (not immediate)

Community detection (Leiden) and GraphRAG pipelines add significant latency and degrade with graph size. Not a current problem, but becomes real at thousands of nodes.

**Mitigation (future):** Graph pruning strategy, node archiving for low-recency/low-confidence observations, tiered retrieval (fast vector approximate first, expensive graph traversal only when needed).

---

## Novelty Assessment

The specific combination Gopher-bot represents does not appear as a packaged system in the literature:
- Persistent identity in a knowledge graph (symbolic slow layer)
- Neuroscience-modeled coordinator architecture (16 coordinators with brain-region analogues)
- Personal governance layer (charter + proposal mechanism + ratification)
- Three-tier cost management with local model fallback
- BCI-ready sensor architecture
- Build/runtime session identity separation

Individual components (PKG, GWT, multi-agent, governance) appear separately. The integration — and particularly the governance layer as a first-class safety mechanism rather than a bolted-on policy — is genuinely novel.

---

## New Tasks Derived from Research (Round 2)

| Task | Description | Derived from |
|---|---|---|
| Task 44 | SCM-informed Dream phases: explicit NREM (strengthen + downscale) + REM (novel association) + scored deletion queue | SCM 2604.20943 |
| Task 45 | D-MEM Critic Router in Neuromodulation: RPE = Surprise + Utility scoring; SystemState.dopamine drives tick frequency | D-MEM 2603.14597 |
| Task 46 | Mirror-Self drift detection: canonical probe set + Hamming hash baseline; runs every 50 sessions via Dream AUDIT | Persistent Identity 2604.09588 |
| Task 47 | Hybrid retrieval routing in Memory: focused queries → vector RAG, relational queries → WaterCircles traversal | Persistent Identity 2604.09588 + PersonalAI 2506.17001 |
| Task 48 | PriorityMap in Awareness bid-gating: P = saliency + emotional valence + recency + goal-alignment; amygdala fast-path for |v| > 0.6 | ZenBrain 2604.23878 |
| Task 49 | Hands policy interception layer + transactional filesystem snapshots: whitelist/greylist/blacklist + rollback buffer | Fault-Tolerant Sandboxing 2512.12806 |
| Task 50 | Two-Factor Synaptic Model for KG edges: add consolidation_variance field (subsumes Task 40 simple decay) | ZenBrain 2604.23878 |
| Task 51 | Pattern Monitor temporal trajectory tracking: slope + curvature per Topic node over N sessions; bid on declining trajectories | Temporal Affective 2601.12341 |

---

## Open Research Questions

1. **Entrenchment detection threshold** — at what point does a stable belief become a concerning entrenchment? Needs an operational definition for Dream's AUDIT step.
2. **Community detection timing** — when in the build sequence does the graph become large enough that Leiden is useful rather than noisy?
3. **WaterCircles vs beam search** — which traversal method is better for Gopher-bot's specific query patterns (relational vs factual)?
4. **Confidence decay curve** — what decay function works best for personal knowledge (linear, exponential, sigmoid)? Task 40 will need to decide.
5. **RPE calibration** — what Surprise + Utility weights produce correct dopamine gating for a single-user companion? Too sensitive → every input is high-RPE; too insensitive → genuine preference shifts go to fast buffer.
6. **Canonical probe set design** — which questions most reliably detect identity drift in a personal AI? Questions must be stable (same answer regardless of mood/context), discriminating (sensitive to actual drift), and short (low inference cost per probe).
7. **NREM downscaling threshold** — at what edge strength / session-age should co-occurrence edges be downscaled vs. preserved? Too aggressive → correct but rare associations are lost; too conservative → noise accumulates.
8. **Neuromodulator tonic baseline calibration** — what tonic levels for DA/NE/5HT/ACh produce the right default behavior for a personal companion? Too much DA (high learning-rate) → system overreacts to everything. Too much 5HT (high consolidation-patience) → Dream never completes in the idle window. Needs empirical tuning post-implementation.
9. **Pattern Monitor trajectory window** — how many sessions constitute a reliable trajectory estimate for a topic? Too few → every short-term fluctuation triggers bids. Too many → real declining engagement is missed. Hypothesis: 5-session minimum, 20-session rolling window.
10. **Hands greylist automation boundary** — which actions are truly safe to automate without Awareness approval vs. which require live gating? Current spec says "file writes" are greylist, but appending to a log file is qualitatively different from overwriting a config. Needs a more granular taxonomy before Hands implementation.

---

## Interface Architecture Design Notes

*(Recorded 2026-05-19. Not from academic literature — architecture decisions from Director session.)*

### Current state of interface/ (as of 2026-05-19)

Phase 1 is essentially complete and committed:
- `interface/server.py` — Flask + SocketIO. Endpoints: `/chat` (POST), `/brain-status` (GET), `/voice` (POST), WebSocket `message`. BrainLoop runs as daemon thread. STT and TTS already plumbed.
- `interface/bot.py` — Awareness wrapper, `synchronous_run()` pipeline entry point
- `interface/stt.py` / `tts.py` — Speech-to-text and text-to-speech modules
- `interface/static/index.html` — Dark-theme web frontend (CSS variables, Inter font, responsive)

C-004 completion criteria is close. What remains: Pattern Monitor coordinator submitting bids, audit panel showing live coordinator activity, first proactive Voice output from BrainLoop without Chad prompt.

---

### Interface Phase Roadmap (C-005)

**Phase 1 — Flask web app (done)**
Chat + voice endpoints. BrainLoop daemon. Static frontend. Gopher-bot as a web app you open.

**Phase 2 — Tauri ambient desktop presence**
Wrap the Flask/SocketIO backend in a Tauri (Rust + webview) desktop app. Key unlock: Sensory gains passive OS-level context — active app, open files, window focus changes — without Chad typing anything. The brain becomes ambient; it runs whether the UI is open or not.

Design constraint for Task 29 (Hands): Hands must be designed with Phase 2 in mind from day one. System-level access patterns (file paths, subprocess scope, network endpoints) should be declared and policy-gated at the Tauri layer, not bolted on after. The fault-tolerant sandboxing pattern (policy interception + transactional snapshots from 2512.12806) maps directly onto Tauri's IPC invoke layer.

**Phase 3 — NixOS-based AI-native environment (the dream)**
Custom Linux distro (NixOS base recommended: declarative, reproducible, purpose-configurable). Key architectural properties:
- Coordinators are systemd services with declared AppArmor/SELinux MAC profiles — Hands whitelist/greylist/blacklist enforced at the kernel level, not in Python
- Build/runtime separation is a user namespace boundary, not a documented convention
- Knowledge graph is the persistence primitive — everything is a node (processes, sessions, observations, outputs, audit entries), not just files in a directory
- Session identity is a first-class OS concept; the Charter's governance model maps onto OS-level audit infrastructure
- Interface is a spatial navigator through the knowledge graph, not a chat window

**Academic precedents worth revisiting for Phase 3:**
- Plan 9 (Bell Labs) — unified namespace where everything including network devices is a file; closest ancestor to "everything is a graph node"
- seL4 — formally verified microkernel with capability security; relevant to Hands execution safety at the OS level
- Genode — OS framework built entirely on capability-based security; coordinator-as-capability maps onto this model

**Intermediate step (before Phase 3, after Phase 2):**
Containerize the coordinator stack. Each coordinator runs in its own container with declared capabilities and mounted volumes. Neuromodulation, graph, and state files are mounted volumes. Container boundaries become the Phase 3 MAC boundaries. This is the right setup step and adds almost no overhead to the current architecture.

---

### Open Design Questions — Interface

1. **Tauri vs. Electron for Phase 2** — Tauri (Rust) is lighter and more secure; Electron has broader ecosystem. For a privacy-first local system, Tauri is the better fit. Decide before Hands is designed.
2. **Passive Sensory input format** — What does Sensory receive from the OS layer? Active window title? File path of focused document? Clipboard content? Needs a declared schema before Tauri integration.
3. **NixOS coordinator service model** — Does each coordinator get its own systemd unit, or does BrainLoop run as a single service managing all ticks? The latter is cleaner given the current architecture; the former gives finer-grained restart/monitoring. Probably single BrainLoop service with coordinator health checks per FM-F mitigation.
4. **Graph-as-persistence OS** — At what point does the knowledge graph replace the filesystem as the primary persistence layer? Probably not until Phase 3 is well underway. In Phase 2, graph + JSON state files coexist. In Phase 3, JSON state files become graph nodes.
