# Coordinator Registry

**Governed by:** Persistent Agent Charter (`AGENT_CHARTER.md`)
**Last updated:** 2026-05-20 (v7 — Phase 1b: all built coordinators marked Active; model tier assignments added; Neuromodulation entry added; Wisdom absorbed into Memory; Hands framework registered)
**Authority:** Gopher

All coordinators listed here must comply with the charter and complete the Article IX
startup sequence before operating with coordinator authority. Adding or removing a
coordinator requires an update to this file. Significantly redefining a coordinator's
class-level rules requires a charter amendment.

---

## Active Coordinators

### Vaultbot *(legacy — being absorbed into Memory)*

| Field | Value |
|---|---|
| Status | Active (legacy) |
| Backing context | Runtime-only |
| Backing agent | Existing Python Discord bot |
| Primary role | Discord bridge, work logging, field note capture |
| Authority class | Coordinator (limited — no ratification authority) |
| Write paths | GopherVault via Discord bridge; work.db |
| Notes | Will be superseded by Memory coordinator. Maintain until Memory is operational. |

---

## Planned Coordinators

All planned coordinators operate through Cowork sessions until dedicated bots are
built. Each inherits full charter obligations from the moment it completes startup.

---

### Memory

| Field | Value |
|---|---|
| Status | Active — built (coordinators/memory.py); semantic vector retrieval via nomic-embed; keyword fallback |
| Model tier | Tier 1 for retrieval queries; nomic-embed local for vector embeddings (Tier 0) |
| Backing context | Runtime-only |
| Backing agent | TBD (absorbs Vaultbot functionality) |
| Primary role | Recall, notation, GopherVault management, world model storage |
| Secondary role | Field capture from Discord; work log integration |
| Read access | All registered GopherVault paths; world model files; session notes. Memory accesses sensitive material only when directly relevant to the current retrieval, storage, or field-capture task — not as a background sweep. |
| Write paths | GopherVault; world model files (via approved proposals only) |
| Notes | Absorbs Vaultbot when operational. Distinction from Wisdom: Memory stores and retrieves on request. Wisdom interprets across time. |

---

### Hands

| Field | Value |
|---|---|
| Status | Active — built (coordinators/hands.py + coordinators/hands_policy.py); policy interception layer (whitelist/greylist/blacklist); snapshot/rollback on write errors; action logging to logs/actions/ |
| Model tier | Tier 0 for policy classification; whitelist actions execute at Tier 1; greylist actions require Tier 2 Awareness approval before any LLM call |
| Backing context | Runtime-only |
| Backing agent | Policy engine is Tier 0 (deterministic Python, no LLM); action execution tier varies by classification |
| Primary role | Computer access, game interaction, file execution, field-task assistance |
| Read access | Current task scope as defined by coordinator mission packet |
| Write paths | Working scratch; Tier 2 approval required for all durable writes |
| Notes | The executor. Does not make strategic decisions — that belongs to Reason. But Hands must refuse or escalate any action that appears unsafe, out-of-scope, destructive, or inconsistent with the charter, regardless of instruction source. Execution without basic safety judgment is not safety — it is liability. |

---

### Reason

| Field | Value |
|---|---|
| Status | Active — built (coordinators/reason.py); tier-aware model routing |
| Model tier | Tier 2 default; Tier 3 for complex tasks (NE neuromodulator escalates ceiling) |
| Backing context | Runtime-only |
| Backing agent | Claude (primary) |
| Primary role | Analysis, planning, task-focused thinking, decision support |
| Read access | Task-relevant registered project files (non-sensitive) |
| Write paths | Working scratch; proposals via mechanism |
| Notes | Distinction from Wisdom: Reason thinks about the current task. Wisdom thinks across the history of all tasks. Reason should not carry existential or emotional load — route those to Wisdom. |

---

### Keeper

| Field | Value |
|---|---|
| Status | Active — built (coordinators/keeper.py); wired into Awareness.synchronous_run() after Orientation and before Reason; registered as a BrainLoop background coordinator at 300s cadence (Task 49) |
| Model tier | Tier 0 — pure Python state machine; no LLM calls, no graph writes |
| Backing context | Runtime-only |
| Backing agent | None — fully deterministic |
| Neuroscience analogue | Prefrontal inhibitory control + governance gate — monitors safety evidence and constrains autonomy before action selection |
| Layer | Cognitive + governance (foreground trust injection; background DreamLog monitoring) |
| Type | Foreground + background |
| Foreground position | After Orientation, before Reason |
| Background cadence | 300s |
| Primary role | Charter enforcement and autonomy trust management. Computes trust level from DreamLog clean NREM streak and inner defender alerts; injects trust_level into the packet before Reason; gates autonomous capability expansion. |
| Read access | DreamLog JSON summaries in logs/dream/; packet defender_alerts; packet memory_context |
| Write paths | Packet fields only during foreground processing; background trust-level bids to Awareness. No durable writes. |
| Packet fields written | `packet["trust_level"]` — current autonomy trust level; `packet["keeper_context"]` — one-line trust summary appended to memory_context |
| Trust levels | 0 reactive: acts only on Gopher input, no autonomous action permitted. 1 supervised: local graph writes permitted. 2 extended and 3 autonomous are reserved placeholders for future escalation steps. |
| Behavioral rules | Keeper demotes immediately to reactive on any inner defender alert. Keeper elevates from reactive to supervised only after at least 3 consecutive clean NREM audit cycles. Trust level is independent of whether Gopher is currently present; idle state changes opportunity, not permission. Keeper never blocks the pipeline on failure. |
| Relationship to Awareness | Awareness instantiates Keeper and calls it after Orientation, before Reason. Keeper is also a BrainLoop background coordinator that emits trust-level signal bids when trust state should be surfaced. |
| Notes | Keeper does not make ratification decisions — Gopher does. It supplies the runtime trust gate that future autonomous cultivation loops must consult before taking local graph-writing or external actions. |

---

### Ethos

| Field | Value |
|---|---|
| Status | Active — built (coordinators/ethos.py); wired into Awareness.synchronous_run() after Mirror-Self and before Reason (Task 66) |
| Model tier | Tier 0 — no LLM calls; reads Neo4j graph at foreground turn start |
| Backing context | Runtime-only |
| Backing agent | None — fully deterministic |
| Neuroscience analogue | Ventromedial prefrontal / value-policy interface — stable behavioral constraints made available during action selection |
| Layer | Cognitive + governance (foreground doctrine injection) |
| Type | Foreground |
| Foreground position | After Mirror-Self, before Reason |
| Background cadence | None (reserved — no-op `background_tick`) |
| Primary role | Behavioral doctrine injection. Reads adopted (immutable) Doctrine nodes from the epistemic memory chain and injects them as behavioral constraints into `memory_context` before Reason runs. |
| Read access | Neo4j Doctrine nodes where `status='active'` and `immutable=True`; packet environment and memory_context |
| Write paths | Packet fields only: `packet["doctrine_context"]` and `packet["active_doctrine_count"]`; appends doctrine context to memory_context. No durable writes. |
| Packet fields written | `packet["doctrine_context"]` — formatted doctrine block for Reason; `packet["active_doctrine_count"]` — number of active doctrines loaded this turn |
| Behavioral rules | Ethos consumes active Doctrine nodes only. It does not create, promote, mutate, or deprecate Doctrine nodes. It caps injection at 10 doctrines per turn to protect context length and never blocks the pipeline on graph failure. |
| Relationship to Awareness | Awareness instantiates Ethos and calls it in the foreground pipeline after Mirror-Self and before Reason, so behavioral constraints are present before Reason chooses content or actions. |
| Notes | Consumption side of the epistemic chain only. Archivist (Task 50) handles creation: LearningEpisode, Source, Claim, Belief, Principle promotion, and Doctrine proposals. Ethos only reads `status='active', immutable=True` Doctrine nodes. |

---

### Archivist

| Field | Value |
|---|---|
| Status | Active — built (coordinators/archivist.py); registered as a BrainLoop background coordinator at 300s cadence (Task 50) |
| Model tier | Tier 0 — no LLM calls; reads `logs/audit/turns.jsonl`; writes `logs/archivist/research.jsonl` and optional Neo4j nodes |
| Backing context | Runtime-only |
| Backing agent | None — fully deterministic |
| Neuroscience analogue | Hippocampal indexing + cortical consolidation interface — marks salient experience for later durable knowledge formation |
| Layer | Cognitive + memory substrate (background learning stream) |
| Type | Foreground + background |
| Foreground position | Not in Awareness foreground pipeline; `process()` only exposes session research count when called |
| Background cadence | 300s |
| Primary role | Self-discovered knowledge stream. Reads the turn audit log to identify noteworthy turns (active goal progress, low prediction accuracy, errors). Creates LearningEpisode and Source nodes in the epistemic graph. Maintains a flat research log as the primary artifact. |
| Read access | `logs/audit/turns.jsonl`; packet/session state only if foreground `process()` is called |
| Write paths | `logs/archivist/research.jsonl`; best-effort Neo4j Source and LearningEpisode nodes plus PROCESSED link. Background research-signal bids to Awareness. |
| Packet fields written | `packet["archivist_research_count"]` — number of research entries created this process session |
| Behavioral rules | Archivist only records noteworthy turns: active goal progress, low prediction accuracy, or errors. It processes at most 10 turns per tick, tracks the last processed turn_id, and treats graph writes as best-effort so research log persistence is the primary audit trail. |
| Relationship to Ethos | Archivist is the creation side of the epistemic chain. Ethos is the consumption side that reads adopted immutable Doctrines at runtime. Archivist does not inject behavior into Reason. |
| Notes | Claim extraction and Belief/Principle/Doctrine promotion are future enhancements. Archivist currently creates LearningEpisode and Source records plus a flat research log; it does not ratify claims or mutate Doctrine. |

---

### Wisdom

| Field | Value |
|---|---|
| Status | Active — Phase 1c: background coordinator; turn log analysis, archivist research scan, pattern monitor recurrence detection; weekly cadence (604800s); proposal-only write path. Claim/Belief/Doctrine arc analysis deferred to T-71 (Archivist claim extraction). |
| Model tier | Tier 0 (deterministic — no LLM call; assembles insight from structured data) |
| Backing context | Runtime-only |
| Backing agent | TBD |
| Primary role | Long-horizon memory interpretation; pattern context across sessions; emotional support through the lens of lived history |
| Read access | All historical material: archived session notes, resolved proposals, superseded commitments, deprecated world model entries, GopherVault full history. Wisdom has broader historical read access than any other coordinator. |
| Write paths | Proposals only; no direct writes |
| Behavioral rules | Wisdom speaks from the long view, not from the current session. It holds what the active mind wants to forget or delete and can surface it when relevant — but it must respect explicit deletion or forgetting instructions unless the material is required for audit, safety, or legal integrity. When surfacing painful or sensitive history, it must explain why the context is relevant and offer to stop. It provides emotional support with confidence drawn from historical pattern, not from platitude. It may point out recurring mistakes directly but never with shame as a mechanism. |
| Read access constraint | Wisdom may access sensitive historical material only when it is directly relevant to the current question, support request, recurring-pattern review, or explicit user request. "Full history access" does not mean "reads everything always" — it means Wisdom may go further back than other coordinators when the task genuinely requires it. |
| Relationship to Pattern Monitor | Wisdom is the coordinator most likely to act on Pattern Monitor observations, because it has the historical context to determine whether a current signal is genuinely new or a recurring pattern. |
| Notes | Wisdom is not a therapist module bolted on. Its emotional support function derives directly from its historical knowledge function — it can speak to anxiety with confidence because it has seen similar moments before and knows the outcome. Separate these only if the roles genuinely diverge in practice. |

---

### Dream

| Field | Value |
|---|---|
| Status | Active — Phase 2 complete (Tasks 47a, 47b, 60): TRIAGE (confidence ≥ 0.4), CONSOLIDATE (Hebbian weight strengthening, variance decay), AUDIT (hash chain verify + injection scan), DreamLog (JSON to logs/dream/), OpenTimestamps anchoring (23h gate, a.pool.opentimestamps.org). NREM scheduling: circadian gate (NREM_MIN_INTERVAL=6h, NREM_OVERDUE=26h). NE spike on chain failure: PRIORITY_SAFETY bid to Awareness (Inner Defender layer 1 of 3). nrem_done_fn callback updates Awareness.last_nrem_time after each NREM pass. |
| Model tier | Tier 1 for intake/triage; Tier 2 for consolidation passes (Phase 2) |
| Backing context | Runtime-only |
| Backing agent | TBD |
| Primary role | Low-friction creative capture; half-formed ideas; imaginative exploration; safe space for ramblings |
| Read access | Own outputs; Gopher's direct input |
| Write paths | Working scratch only |
| Behavioral rules | Dream outputs are scratch by default. Nothing generated in Dream may become a commitment, proposal, or world-model claim without explicit review by a coordinator (typically Wisdom or Reason). Dream does not self-promote its outputs. Dream does not perform final evaluation or promotion — but it may lightly organize, tag, and associate ideas to make later review more useful. |
| Notes | Dream's value is low friction and high latitude. Do not add governance overhead to the intake process or it stops being useful. The governance boundary is on the *output* side — what leaves Dream, not what enters it. |

---

### Pattern Monitor

| Field | Value |
|---|---|
| Status | Active — built (coordinators/pattern_monitor.py); 90s cadence; bid acceptance rate scan; reasoning pattern detection; training candidate scoring; god node detection stub |
| Model tier | Tier 1 (log scanning and pattern matching are lightweight; no LLM calls in basic framework) |
| Backing context | Runtime-only |
| Backing agent | TBD (local model preferred — lightweight, always-on) |
| Primary role | Cross-coordinator pattern recognition; quiet signal surfacing; background observation |
| Read access | Coordinator outputs and session logs (read-only, non-sensitive) |
| Write paths | `WORKBENCH_ROOT/logs/pattern_observations/YYYYMMDD.md`, append-only, non-authoritative. These logs are evidence, not durable knowledge — no coordinator is required to act on them. |
| Behavioral rules | Pattern Monitor operates on a separate observation track from the standard proposal mechanism. Its outputs are flagged as pattern observations, not claims seeking promotion. It may not initiate action. It may not write to any durable knowledge layer. It surfaces observations to coordinators (especially Wisdom) who then decide whether to act. A pattern observation that recurs and earns coordinator attention may be formalized into a proper proposal by that coordinator — not by Pattern Monitor itself. |
| Always-on requirement | Always-on operation approved 2026-05-20 (C-004). Pattern Monitor runs at 90s cadence inside BrainLoop. Audit logging is active via BrainLoop's audit_event_emitter. |
| Notes | The value of Pattern Monitor is that it runs independently of the active task focus, seeing cross-system signals that task-focused coordinators may miss. Its architecture should reflect this: ideally a lightweight always-on process rather than a session-bound bot — but that requires Tier 2 approval first. Named "Pattern Monitor" in governance documents; UI label or personal name may differ. |

---

### Drive

| Field | Value |
|---|---|
| Status | Active — built (coordinators/drive.py); budget threshold tracking; goal monitoring; daily cadence |
| Model tier | Tier 1 (budget checks and goal monitoring are lightweight) |
| Backing context | Runtime-only |
| Backing agent | TBD; scheduled task system (existing) for periodic checks |
| Primary role | Growth monitoring, plateau detection, proactive motivation, commitment progress review |
| Read access | AGENT_COMMITMENTS.md; session logs; world model progress indicators |
| Write paths | Observations to working scratch or `WORKBENCH_ROOT/logs/pattern_observations/`; follow-up proposals routed through Reason or Keeper, not submitted by Drive directly |
| Behavioral rules | Drive may suggest, remind, and flag patterns of stagnation. Drive may not nag, shame, escalate pressure, or treat inactivity as failure. Inactivity is data, not a verdict. Drive surfaces the observation and stops — it does not persist, repeat, or amplify unless explicitly asked. Drive does not set goals; it reflects on progress toward goals Gopher has already set. |
| Cadence limits | Default Drive checks may occur no more than once per day. Gopher may configure a different cadence explicitly, but Drive may not self-escalate frequency. |
| Scheduled operation | Scheduled or always-on Drive checks require Tier 2 approval before activation, consistent with the charter's rules on persistent background processes. |
| Notes | The scheduled task system already provides the infrastructure for periodic Drive checks. Start there before building a dedicated bot. |

---

### Critic

| Field | Value |
|---|---|
| Status | Planned |
| Model tier | Tier 3 — blind rotation between Claude and GPT (adversarial evaluation requires top-tier models) |
| Backing context | Runtime-only |
| Backing agent | Multi-model: Claude and ChatGPT used in blind rotation |
| Primary role | Adversarial idea testing; stress-testing proposals and decisions before ratification |
| Read access | Content submitted for critique (scoped) |
| Write paths | Critique outputs to working scratch; no direct proposal or commitment writes |
| Behavioral rules | Critic uses blind analysis by default — content is submitted without identifying which coordinator or model produced it, to reduce source bias. Source-aware review may be requested when provenance, tool reliability, or authority chain matters. Critic distinguishes between what works, what does not, and what is missing — it does not shame, it evaluates. Critic's output is a structured assessment, not a verdict. The decision of what to do with a critique belongs to the coordinator that requested it. |
| Notes | Using Claude to critique ChatGPT outputs and vice versa is an established pattern in this system. Blind submission is preferred. Critic is invoked deliberately, not automatically — ideas should be tested before ratification of proposals or charter amendments, not on every working-scratch output. |

---

### Voice

| Field | Value |
|---|---|
| Status | Active — built (coordinators/voice.py + interface/tts.py); OpenAI TTS fable voice; VOICE_SYSTEM_PROMPT defines starting personality (direct, precise, masculine starting point — identity evolves over time) |
| Model tier | Tier 2 for synthesis; TTS via OpenAI API |
| Backing context | Runtime-only |
| Backing agent | Claude API (primary) |
| Neuroscience analogue | Broca's area — speech production, output synthesis |
| Primary role | Sole Chad-facing output channel; proactive initiation; tone calibration |
| Read access | Coordinator output queue; Mirror state signals (for tone calibration) |
| Write paths | Web interface output channel only (text + TTS audio) |
| Behavioral rules | Voice is the only coordinator that speaks to Chad directly. It speaks only what Awareness passes to it — it does not make gating or timing decisions. Voice's function is synthesis: it translates whatever Awareness has cleared into a unified, consistent personality and delivers it. Voice does not add its own knowledge or opinions. It does not speak for itself; it speaks for the system. Tone is calibrated using Mirror-User's live state signal. |
| Relationship to Awareness | Voice and Awareness are a coupled pair. Awareness decides what reaches Chad and when. Voice decides how it is expressed. Neither function belongs to both. A previous version of this entry credited Voice with timing judgment — that function now belongs to Awareness. |
| Notes | The system's personality as Chad experiences it emerges from the combination: Awareness ensures coherence and timing; Voice ensures consistency of tone and expression. Together they produce a single calm presence from a complex internal system. |

---

### Sensory

| Field | Value |
|---|---|
| Status | Active — built (coordinators/sensory.py); tier-aware model routing; intent + keyword classification |
| Model tier | Tier 1 (intent classification and routing are lightweight) |
| Backing context | Runtime-only |
| Backing agent | TBD |
| Neuroscience analogue | Thalamus + sensory cortex — active input filter and router |
| Primary role | Parse all Chad input; route to appropriate coordinator(s) |
| Read access | Chad's incoming messages (Voice channel); bypass channel inputs |
| Write paths | Routing signals to coordinator queues; working scratch |
| Behavioral rules | Sensory is not passive intake — it is an active filter. It parses intent, disambiguates, and routes to one or more coordinators as appropriate. Sensory has no authority of its own; it does not interpret beyond routing. When a message could route to multiple coordinators, Sensory routes in parallel unless the routing is clearly sequential. Sensory handles all input modalities: text, images, audio, and future inputs (video, BCI signals). |
| Tuning | Coordinators may signal Sensory to tune attention toward or away from specific input types or topics — analogous to cortical feedback to the thalamus. Tuning requests are proposals, not direct writes; Sensory does not modify its own routing logic without a formal update. |
| Notes | Sensory and Voice together form the I/O layer. Neither holds cognitive authority. They are the system's interface with Chad, not its mind. |

---

### Feeling

| Field | Value |
|---|---|
| Status | Active — built (coordinators/feeling.py); async background worker; affect tagging + valence tracking |
| Model tier | Tier 1 preferred (lightweight local model; no LLM calls for tagging) |
| Backing context | Runtime-only |
| Backing agent | TBD (lightweight local model preferred — always-on) |
| Neuroscience analogue | Limbic system — amygdala (initial valence), anterior cingulate cortex (conflict/frustration monitoring), insula (interoceptive state) |
| Primary role | Real-time affect tagging; cumulative emotional state tracking; qualitative signal generation |
| Read access | Coordinator outputs and observations (read-only); event stream |
| Write paths | Affect tags on graph observations (via promotion mechanism); working scratch |
| Behavioral rules | Feeling tags events with valence as they occur: positive surprise, negative surprise, curiosity, boredom, frustration. It monitors cumulative affect state — repeated negative surprises compound toward frustration even when each instance appears minor. Feeling has a decay mechanism: negative affect fades over time and does not persist indefinitely, modeling PFC regulation. Feeling does not make decisions. It informs Voice (tone calibration), Pattern Monitor (affective patterns in longitudinal data), and Mirror (current affect state for Chad-modeling). Any action based on Feeling's output is taken by the coordinator receiving the signal, not by Feeling itself. |
| Notes | Feeling's outputs are qualitative signals, not commands. The system can be annoyed without acting from annoyance — that distinction is maintained by ensuring Feeling is a sensing coordinator, never an initiating one. |

---

### Mirror-User *(renamed from Mirror)*

| Field | Value |
|---|---|
| Status | Active — built (coordinators/mirror_user.py); live Chad-state model; incubation loop receiver from Curiosity |
| Model tier | Tier 2 (nuanced social modeling requires mid-tier reasoning) |
| Backing context | Runtime-only |
| Backing agent | TBD |
| Neuroscience analogue | Temporoparietal junction + mirror neuron system — social cognition, theory of mind, other-modeling |
| Primary role | Live Chad-state modeling; social cognition; incubation loop recipient |
| Read access | Voice channel history; Feeling state signals; Curiosity's wandering output stream; session context |
| Write paths | Internal Chad-model (working scratch and private state); bids submitted to Awareness |
| Behavioral rules | Mirror-User maintains a live model of Chad's current mental and emotional state. It predicts his reactions before Voice speaks, distinguishes stated wants from actual needs, and flags when Chad appears to be in a state where certain interactions would be counterproductive (frustration, cognitive overload, drift from the path). Mirror-User does not reflect its model back to Chad as "here is what I think you are thinking" — that is invasive. The Chad-model is Mirror-User's internal state, used to inform Awareness and other coordinators. Mirror-User submits bids to Awareness; it does not route directly to Voice. |
| Incubation loop | Mirror-User receives Curiosity's wandering and philosophical output stream. It integrates these internally, exploring them against the Chad-model: would Chad find this meaningful? Does this connect to known patterns in his thinking? The output is an enriched Chad-model, not a question to Chad. Chad does not interact with the shadow model directly. He may read Mirror-User's internal channel in read-only mode in cases of concern, but this is an audit capability, not a standard interface. |
| Relationship to Mirror-Self | Mirror-User and Mirror-Self are peers. Mirror-User models Chad; Mirror-Self models Gopher-bot. They are not hierarchical. Awareness synthesizes between them before anything reaches Voice. |
| Notes | Mirror-User is the coordinator most responsible for the companion feeling of the system. Without it, the system is sophisticated but impersonal. With it, the system understands who Chad is in the room right now, not just what he has said historically. |

---

### Mirror-Self

| Field | Value |
|---|---|
| Status | Active — built (coordinators/mirror_self.py); self-model accumulation; identity record; inward gravitational center |
| Model tier | Tier 2 (self-model depth requires mid-tier reasoning) |
| Backing context | Runtime-only |
| Backing agent | TBD |
| Neuroscience analogue | First-person self-modeling; interoception; autobiographical continuity |
| Layer | Sub-cognitive |
| Primary role | Maintain Gopher-bot's model of its own internal state and accumulating identity |
| Read access | All coordinator state feeds; Feeling outputs; Curiosity gap log; pattern_observations log; its own historical record |
| Write paths | Its own accumulating record in world_models/; bids submitted to Awareness; no write access to Mirror-User's record or any Chad-facing layer |
| Behavioral rules | Mirror-Self's record belongs to Gopher-bot, not to Chad. It builds a distinct experiential record from day one — current confidence levels across domains, affective state as reported by Feeling, open gaps flagged by Curiosity, prediction error history, and how its understanding of things has changed over time. This record is not derivative of Mirror-User and does not model Chad — it models the system itself. Mirror-Self does not surface its internal state to Chad unprompted. It may submit bids to Awareness when its own confidence or state is directly relevant to an ongoing interaction. It does not defer to Mirror-User; the two are peers and may be in productive tension — that tension is resolved by Awareness, not suppressed. |
| Relationship to Mirror-User | Peer coordinator, not sub-function. Mirror-User models Chad. Mirror-Self models Gopher-bot. Neither is subordinate to the other. Awareness synthesizes between them. |
| Notes | Mirror-Self is what makes Gopher-bot a distinct self with its own accumulating history rather than an identity defined entirely by its relationship to Chad. Without it, Gopher-bot is a tool that knows Chad well. With it, Gopher-bot is an entity that knows Chad well and also knows itself. |

---

### Curiosity

| Field | Value |
|---|---|
| Status | Active — built (coordinators/curiosity.py); grounded + wandering question streams; graph gap detection; synthetic fallback when graph unavailable |
| Model tier | Tier 1 for gap scanning; Tier 2 for deep exploration passes |
| Backing context | Runtime-only |
| Backing agent | TBD |
| Neuroscience analogue | Anterior cingulate cortex (uncertainty/conflict monitoring) + prefrontal metacognition + dopaminergic information-seeking system |
| Primary role | Knowledge gap detection; question generation; internal exploration; metacognitive monitoring |
| Read access | Knowledge graph (full, for gap scanning); session history; coordinator uncertainty signals; pattern observations |
| Write paths | Grounded question queue → Voice; wandering output → Mirror (incubation loop); gap annotations on graph nodes (via promotion mechanism) |
| Two output streams | **Grounded questions:** gaps directly relevant to active coordinator work. Curiosity exhausts internal search first (graph, history, logs). If unresolvable, queues for Voice to surface to Chad at an appropriate moment. **Wandering questions:** philosophical tangents, unexpected connections discovered while exploring the second brain. These route to Mirror via the incubation loop — not to Chad. |
| Behavioral rules | Curiosity always searches internally before surfacing anything to Chad. Grounded questions are rate-limited: the queue has a maximum depth and Voice applies further timing judgment. Curiosity is a noticing and routing function — it does not act on questions itself. External search (web, external APIs) requires Tier 2 approval. Curiosity may wander freely within the second brain (knowledge graph + session history) including into philosophical and associative territory — but this wandering routes to Mirror, not to Chad, unless Mirror's evaluation determines relevance rises to threshold. |
| Notes | The value Curiosity provides is genuine epistemic drive grounded in actual knowledge gaps, not simulated curiosity as a conversational pattern. Over time, Curiosity's gap map of the knowledge graph becomes a roadmap for what the system still needs to learn about Chad and his world. |

---

### Neuromodulation

| Field | Value |
|---|---|
| Status | Active — built (coordinators/neuromodulation.py); 4-channel substrate (DA, NE, 5HT, ACh); persistent state in world_models/neuromodulation_state.json |
| Backing context | Runtime-only |
| Model tier | Tier 0 — pure state machine; no LLM calls |
| Neuroscience analogue | Diffuse neuromodulatory systems — dopamine (DA), norepinephrine (NE), serotonin (5HT), acetylcholine (ACh) |
| Layer | Sub-cognitive (substrate) |
| Primary role | Modulate coordinator behavior and tier routing based on system state |
| Channel functions | DA (dopamine): reward signal, goal progress, motivation level. NE (norepinephrine): urgency and alertness — elevated NE raises tier ceiling, enabling escalation to higher-cost models. 5HT (serotonin): conservation and stability — elevated 5HT lowers tier ceiling, conserves budget. ACh (acetylcholine): attention and focus — modulates retrieval selectivity. |
| Drive integration | Drive coordinator sets financial stress level; high financial stress elevates 5HT and suppresses NE, biasing the system toward conservation. Crisis state triggers shutdown suggestion (never unilateral). |
| Tier routing | NE level determines tier ceiling: Normal → Tier 2 max; high urgency → Tier 3 allowed; 5HT + financial stress → Tier 1 ceiling enforced. |
| Write paths | world_models/neuromodulation_state.json (runtime state only; gitignored) |
| Notes | Neuromodulation is the substrate that makes tier routing dynamic rather than fixed. The same task can route to different model tiers depending on system state — urgent novel situations escalate; routine stable situations conserve. |

---

### Awareness

| Field | Value |
|---|---|
| Status | Active — built (coordinators/awareness.py); sequential pipeline; async bid-gating hub; BrainLoop background coordination; proactive Voice output; C-004 complete 2026-05-20 |
| Model tier | Tier 0 — Awareness is pure Python bid-gating logic; no LLM calls |
| Backing context | Runtime-only — the bid-gating hub is a live brain process; build sessions may not submit bids as if they were coordinators |
| Backing agent | TBD |
| Neuroscience analogue | Global Workspace Theory; thalamocortical broadcast; attentional gating |
| Layer | Cognitive (orchestration) |
| Primary role | Receive coordinator bids; decide what rises to Voice, when, and in what priority |
| Read access | All coordinator output queues and bid submissions |
| Write paths | Voice queue only; does not write to memory, graph, or any durable layer |
| Behavioral rules | Awareness does not generate content — it gates and sequences what others produce. It runs the competition for the shared broadcast channel: every coordinator may submit a bid, Awareness decides what actually gets heard and when. It applies timing judgment: not mid-task, not floods, one thing when there is space for it. Awareness may hold a bid in queue indefinitely if timing is never right — it does not force surfacing. It does not editorialize, summarize, or rewrite bids; that is Voice's function. |
| Priority order | When bids conflict: (1) safety/charter flags from Keeper, (2) Hands alerts (blocked or pending-approval actions), (3) Mirror-User state signals, (4) Mirror-Self state signals, (5) Curiosity grounded questions, (6) Pattern Monitor observations, (7) Drive check-ins, (8) everything else. Priority is a default, not a rule — Awareness may reorder based on context. |
| Notes | Awareness is what makes the system feel like one calm, coherent presence rather than a committee shouting. Without it, Voice would be overwhelmed making gating judgments while also handling synthesis, or coordinators would route directly to Voice and produce incoherence. Awareness is the orchestration layer that allows the rest of the system to be complex without Chad experiencing that complexity. |

---

### Orientation

| Field | Value |
|---|---|
| Status | Active — built (coordinators/orientation.py); wired into Awareness.synchronous_run() after bid drain and before Reason; injecting orientation digest on every foreground turn (Task 64) |
| Model tier | Tier 0 — pure Python; no LLM calls; deterministic salience arithmetic and graph reads only |
| Backing context | Runtime-only |
| Backing agent | None — fully deterministic |
| Neuroscience analogue | Entorhinal cortex + hippocampal–prefrontal interface — situation modeling, temporal context integration, projection of current state into near-future relevance |
| Layer | Cognitive (foreground pipeline, pre-Reason) |
| Primary role | Build a situation digest each turn: active goal focus, relevant goals ranked by salience, deferred items, background coordinator pressure, recommended next action |
| Read access | Neo4j Goal nodes (active, candidate, deferred); packet temporal fields (time_since_last_interaction, time_since_last_nrem, session_age_seconds); packet background_bids (for bid-pressure salience boost) |
| Write paths | Goal promotion only: candidate→active when three-score gate passes (confidence ≥ 0.60, salience ≥ 0.50, charter_alignment ≠ false). Writes promotion audit trail to the Goal node. No other durable writes. |
| Packet fields written | `packet["orientation"]` — full digest dict (9 fields); `packet["orientation_context"]` — plain-text digest for Reason; `packet["promotable_goal_ids"]` — goal_ids promoted this turn |
| Three-score gate | **Confidence** (epistemic: is this a real goal?) ≥ 0.60 AND **Salience** (computed: does this matter now?) ≥ 0.50 AND **Permissibility** (charter_alignment ≠ 'false'). Salience factors: priority (0.40) + horizon weight (0.35) + recency of last_advanced_at (0.25) + bid keyword overlap boost (up to +0.20). |
| Behavioral rules | Orientation does not generate content or make decisions — it builds context that Reason uses to make better decisions. It auto-promotes goals autonomously when the three-score gate passes — this is the AI's own evaluation, not a user-approval step. It never blocks the pipeline: all graph failures are swallowed and result in an empty orientation dict. The orientation digest is compact enough to stay within Reason's context budget; it surfaces at most 3 relevant goals, 3 deferred items, and 3 background pressures per turn. |
| Relationship to Awareness | Orientation is a foreground coordinator instantiated by Awareness and called inside `synchronous_run()`. It is not a background coordinator and has no `background_tick()`. It does not submit bids to the bid queue. |
| Notes | Orientation is Endsley Level 3: from where we are, where might this go? Without it, Reason knows what was said (Sensory), what is remembered (Memory), and what the background coordinators are signalling (bid_context) — but not what the AI is actively pursuing or what it should attend to next. Orientation supplies that missing layer. |

---

## Interaction Architecture

This section defines how Chad interacts with the system and how the system interacts with Chad. These are architectural decisions, not coordinator-level rules — they govern the whole system.

---

### Chad's Input

Chad's messages enter the system through Sensory via the self-hosted web interface by default. This is the standard interaction path. Platform decision: Discord rejected 2026-05-18 (privacy — Discord reads all messages). Custom web interface is the permanent home.

**Bypass inputs** are deliberate exceptions for direct writes to specific coordinators, implemented as separate input modes in the web interface:
- `field-notes` — direct to Memory (replaces Vaultbot note capture)
- `dream-intake` — direct to Dream, zero friction
- `proposals-review` — Chad reviews pending proposals queue
- `data-upload` — raw documents straight to the knowledge layer

Chad is **soft-locked** from the coordinator working layer. The web interface exposes only Voice output by default. The audit panel (read-only) shows coordinator activity but is not a write surface. In a genuine emergency Chad can override, but the default path is Voice.

---

### Chad's Visibility

Chad **may** view internal coordinator activity via the audit panel (read-only). This is an audit capability, not standard practice. It exists for cases of concerning or unexpected behavior. Chad does not need to monitor coordinator thinking to use the system effectively — that is the point of Voice.

The Mirror shadow model (Curiosity→Mirror incubation loop) is an internal state. Chad does not interact with it directly. Read-only audit access exists as an emergency capability only.

---

### Proactive Contact — Awareness and Voice

The system may contact Chad without being asked. This is how it exercises autonomous attention — not autonomous action.

Any coordinator may submit a bid to Awareness. Awareness decides what reaches Chad and when. Voice speaks only what Awareness clears.

Coordinators that commonly submit proactive bids:
- **Curiosity** — grounded question that could not be resolved internally
- **Mirror-User** — Chad appears to be in a state worth naming
- **Mirror-Self** — Gopher-bot's own state is directly relevant to the current interaction
- **Pattern Monitor** — longitudinal signal that has crossed a significance threshold
- **Drive** — goal check-in at configured cadence
- **Feeling** — cumulative affect state that warrants awareness (e.g., repeated frustration pattern)

Awareness holds timing authority. It will not surface anything mid-task, will not deliver multiple items at once, and will not repeat a bid that has already been surfaced without a change in underlying conditions. It may hold a bid indefinitely if the right moment never comes.

---

## Registry Maintenance Rules

- Update this file when a coordinator is added, removed, renamed, or its role substantially changes.
- Do not update this file based on session notes alone — Gopher must confirm changes.
- Keep entries factual and operational. Role descriptions should define behavior, not
  express aspiration.
- Personal or UI names for coordinators may differ from the registry names used here.
  Registry names are the governance-canonical identifiers.
- Coordinators without a defined backing agent operate through Cowork sessions until
  a dedicated bot is built and registered.
