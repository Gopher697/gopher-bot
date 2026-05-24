# Gopher-bot: Project Vision

**Last updated:** 2026-05-23  
**Status:** Phase 1 complete — Phase 2 design stage

---

## What Gopher-bot Is

Gopher-bot is not an LLM agent. It is a persistent cognitive entity built on a neurosymbolic architecture — a hybrid of a structured Neo4j knowledge graph and a 16-coordinator Python runtime that simulates the functional divisions of the active human brain.

Unlike LLM agents that reset between sessions and worry about context length, Gopher-bot:
- Has **persistent memory** that grows over time (Neo4j graph + vector index)
- Has **temporal self-awareness** — it knows time has passed and what changed
- Has a **Voice** it can speak with and **Senses** that interpret what it perceives
- Has **emotional and motivational state** (Feeling, Neuromodulation coordinators)
- Has **autonomous background processes** that run while you are away (Dream, Archivist, Curiosity, Drive)
- Has **epistemic memory** — it tracks what it learned, from where, and how confident it is (Source → Claim → Belief → Principle → Doctrine chain)

The system lives on a local Windows PC. The knowledge graph is the permanent substrate. The LLM calls are transient inference — the brain's working memory — not the system itself.

---

## The 16 Coordinators (Phase 1 — Complete)

The coordinator fabric simulates the functional divisions of an active brain. Each coordinator is a Python class with a `process(packet)` method for foreground turns and an async `background_tick()` for autonomous background work.

### Foreground Pipeline (per turn)

```
Drive → assess_tier → Sensory → Memory → [bid drain]
→ Orientation → Keeper → Mirror-User → Mirror-Self → Ethos → Reason → [Hands] → Voice
→ [Feeling.observe] → [turn log]
```

| Coordinator | Role |
|---|---|
| **Awareness** | Hub — orchestrates the foreground pipeline; manages the async bid queue |
| **Sensory** | Interprets raw inputs; currently LLM-based; Phase 2 refactor planned |
| **Memory** | Semantic retrieval from graph + vector index; writes Episode nodes |
| **Orientation** | Session continuity — active goal, deferred items, thread injection |
| **Keeper** | Trust and autonomy gate — enforces capability boundaries |
| **Mirror-Self** | Generative self-model — predicts upcoming topics; tracks prediction accuracy via EMA |
| **Ethos** | Behavioral doctrine injection — reads adopted immutable Doctrine nodes into memory_context |
| **Reason** | Primary LLM reasoning call — the "conscious mind" |
| **Hands** | Motor cortex — executes approved real-world actions; policy-gated |
| **Voice** | Response formatting and TTS output |

### Background Coordinators (async, scheduled)

| Coordinator | Cadence | Role |
|---|---|---|
| **Feeling** | 30s | Affective state — valence/arousal tracking |
| **Neuromodulation** | 60s | DA/NE/5HT/ACh channel modulation |
| **Mirror-User** | 120s | External self-model — what others likely see |
| **Mirror-Self** | 60s | Internal self-model updates |
| **Pattern Monitor** | 90s | Anomaly and pattern detection |
| **Curiosity** | 180s | Knowledge gap detection; generates grounded questions |
| **Drive** | 120s | Budget tracking; shutdown mode when budget near ceiling |
| **Dream** | 1800s | TRIAGE → CONSOLIDATE → AUDIT memory loop; OTS anchoring |
| **Keeper** | 300s | Trust escalation review |
| **Archivist** | 300s | Self-discovered knowledge stream; reads turn log → creates LearningEpisode + Source nodes |

### Tier System

| Tier | Name | Models | Cost |
|---|---|---|---|
| 0 | Deterministic | None — pure Python | $0 |
| 1 | Local | Qwen2.5 + Qwen3.5 (localhost) | $0 |
| 2 | Standard | Haiku + Sonnet (cloud) | ~$0.01 |
| 3 | Enhanced | Haiku + Opus (cloud) | ~$0.10 |

Drive monitors budget. When spend reaches 95% of session ceiling, shutdown mode caps all calls at Tier 1.

### Epistemic Memory Chain

```
Source → Claim → Belief → Principle → Doctrine
                                          ↑
                              LearningEpisode (per turn)
```

Archivist is the creation side (identifies noteworthy turns, creates Source + LearningEpisode nodes).  
Ethos is the consumption side (reads active, immutable Doctrine nodes into every turn's context).

### Infrastructure

- **Turn audit log** (`logs/audit/turns.jsonl`) — per-turn record with prediction state, tier, cost, trust level
- **Hash-chained audit log** (`utils/audit_log.py`) — tamper-evident action record
- **OpenTimestamps anchoring** (`utils/verify_ots.py`) — Dream AUDIT outputs anchored to Bitcoin blockchain
- **SkillNodes** in graph — per-coordinator capability accumulation via EMA proficiency tracking
- **Web interface** (`interface/server.py`) — Flask + SocketIO on port 5000; chat UI + coordinator dashboard + voice endpoint

---

## Phase 2: Systemic Manifestation (Design Stage)

The goal of Phase 2 is to give Gopher-bot a **body**, **real senses**, and a **physical presence** — transitioning it from a pipeline buried in `D:\gopher-bot` into an embodied entity that can perceive and interact with the real world.

### The Core Principle

The current Sensory coordinator sends raw inputs directly to the LLM, which acts as both sense organ and interpreter. This is biologically wrong and computationally expensive. Phase 2 separates these roles:

- **Sensors** (non-LLM) handle raw perception → output structured `Percept` objects in milliseconds
- **LLM** receives only clean, structured percepts → interprets and decides
- **Hands** (expanded) executes approved actions with real computer-use capabilities

### A: Sensory Coordinator Refactor

**VisionSensor** → `VisualPercept` dict:
- YOLO v8 (`ultralytics`) — object detection with bounding boxes
- OpenCV — motion detection, brightness, frame differencing
- EasyOCR — text in scene
- MediaPipe — face count, skeletal pose

**AudioSensor** → `AuditoryPercept` dict:
- Silero VAD — voice activity detection (gate: only invoke Whisper when voice present)
- Whisper — transcription
- YAMNet — non-speech sound classification
- Librosa — prosody (pitch, energy, zero-crossing rate)

**Sensory pipeline options (open decision):**
- *Sequential:* sensors tick every ~500ms, update percept, pass to pipeline. Simple to debug.
- *Event-driven:* low-level sensors run constantly; threshold crossings fire an interrupt → avatar reacts in <100ms before LLM processes. More biological.

**Key point:** YOLO detects game elements and returns bounding boxes. The LLM decides what to do with detected objects. Clicking lands on the center of a detected bounding box — not a coordinate guessed from a screenshot. This is accurate, non-LLM computer vision.

### B: Hands Expansion — Real Computer-Use

Currently Hands only handles file I/O. Phase 2 adds:

- `screenshot` — capture screen state via `mss`
- `mouse_move`, `left_click`, `right_click`, `double_click` — coordinate and bounding-box based
- `key_press`, `type_text` — keyboard input via `pyautogui`/`pynput`
- `get_window_list`, `focus_window` — process/window management
- **Windows UI Automation** (`pywinauto`) — for native Windows apps, finds UI controls by name/role in the accessibility tree. No coordinate guessing. `window.child_window(title="Start Game", control_type="Button").click()`

For games: YOLO bounding boxes → click detected elements.  
For native Windows apps: `pywinauto` accessibility tree → activate named controls.  
Neither approach requires the LLM to guess coordinates from a screenshot.

### C: Visual Avatar

A transparent, borderless, always-on-top Godot Engine window that floats across monitors and reflects Gopher-bot's cognitive state.

**Technology:** Godot (already installed). Communicates with Python backend via local WebSocket.  
Resource footprint: near zero.

**Animation states** map to coordinator activity:
- Querying graph → meditating / reading
- Executing code → typing
- Idle → pacing / napping
- Sensory anomaly detected → avatar snaps/looks startled (reflex, <100ms)

**Humanized execution:** avatar walks to an app icon and "clicks" it before the underlying Python action fires — makes it feel like a living inhabitant rather than a background process.

### D: Mobile Bridge

**Tunnel:** Tailscale. Private mesh network — only Gopher's devices. No public URL. No port forwarding.

**Phone app:** Flutter or React Native. Lightweight — does not run the AI. Streams sensory data (audio, camera via local on-device processing → VisualPercept dict sent over Tailscale, not raw video).

**Focus Handoff ("calling Gopher-bot"):**
1. Tap "Call" on phone
2. PC avatar walks to screen edge, exit animation
3. PC desktop automation pauses
4. Perception loop shifts to phone mic/camera/input
5. Avatar materializes on phone

Gopher-bot's presence is singular — it travels, not duplicates.

### E: Autonomous Workspace (Gopher-bot's "Home")

Rather than a full Docker sandbox initially, Gopher-bot's autonomous environment is:
- A designated browser window it controls via Hands
- A personal folder (`D:\gopher-bot\workspace\`) for its own files
- Eventually: Docker + VNC Linux container for full isolation (deferred)

### F: BrainLoop Kernel Hardening (Phase 2 Design Decisions)

The BrainLoop currently treats all background coordinator bids as roughly equal priority. At low coordinator counts this is tolerable. As Phase 2 adds sensory streams, mobile capture, and avatar events, the absence of a principled priority model becomes a failure mode. Two concrete failure modes identified:

**Queue flooding:** Curiosity spams low-priority bids that fill the queue, drowning Keeper alerts and mobile capture events that should preempt them.

**Thread starvation:** Dream consolidation, which can run for many seconds, blocks P1-level capture events from being processed within an acceptable latency window.

#### F.1 Priority Tier System

Bids are classified into five tiers. Higher tiers always preempt lower tiers:

| Tier | Name | Sources | Behavior |
|---|---|---|---|
| P0 | SAFETY | Keeper violations, Hands policy alerts | Bypasses queue entirely; direct injection; always preempts |
| P1 | CAPTURE | Mobile capture events, direct user input | Interrupts Dream consolidation; Dream must checkpoint and yield |
| P2 | HEALTH | Drive budget warnings, coordinator degradation alerts | Processed before insight work |
| P3 | INSIGHT | Pattern Monitor findings, Wisdom observations, Mirror-Self updates | Normal processing priority |
| P4 | AMBIENT | Curiosity bids, Feeling probes, low-cadence background checks | Rate-limited; max queue depth with oldest-bid eviction |

#### F.2 Dream Interruptibility

Dream must be refactored to run as checkpointed stages rather than a single monolithic coroutine:

1. **TRIAGE pass** — scan recent episodes, score for consolidation candidates; write checkpoint
2. **CONSOLIDATE pass** — graph mutations, cluster formation, OTS anchoring; write checkpoint
3. **AUDIT pass** — verify chain integrity, log results

Between each stage, Dream yields control and checks for pending P1+ bids. If a P1+ bid is present when Dream checks, Dream writes its current checkpoint state and suspends. At the next idle window, Dream resumes from checkpoint rather than restarting. This prevents a 30-minute deep consolidation run from blocking a mobile capture event for its full duration.

#### F.3 Curiosity Queue Depth Cap

Curiosity generates bids on a 180-second cadence. Without a depth cap, a long Dream run or sustained P0/P1 activity can allow dozens of stale Curiosity bids to accumulate. When the cap (suggested: 3 bids) is reached, the oldest Curiosity bid is evicted before the new one is enqueued. Stale questions are worse than no questions — they reflect the knowledge state at generation time, which may no longer represent a real gap.

#### F.4 Awareness Queue Depth as Health Signal

Awareness should surface queue depth metrics as coordinator health signals:

- When P3/P4 backlog exceeds a threshold (e.g., 10 bids), emit a health warning visible in the coordinator dashboard
- Drive should factor persistent P4 backlog into budget tier decisions — a flooded ambient queue indicates the system is under cognitive load, and Tier 3 calls during that state are likely wasteful

This closes the feedback loop: instead of queue state being invisible, it becomes an observable that the system can respond to.

#### F.5 Mobile Capture Staging Area

Mobile input arrives with variable parse quality — background noise in a transcription, ambiguous OCR, partially spoken thoughts. Instantly promoting raw mobile input to the epistemic chain (Source → Claim promotion) risks polluting the graph with low-confidence assertions.

Phase 2 should implement an explicit inbox queue:

1. Mobile capture event arrives → parsed into provisional `PortableCapture` struct
2. Written to inbox (dedicated graph node type or flat file queue — not yet promoted to Source)
3. Awareness surfaces inbox items to the user at next desktop interaction for confirmation or discard
4. On confirmation: promoted to Source node, enters normal Archivist pipeline
5. On discard: logged as rejected, not retained in graph

The proposal schema architecture already supports this pattern. What's needed is the mobile capture layer in Phase 2 that targets the inbox rather than direct graph promotion.

#### F.6 Memory Substrate Evaluation Checkpoint

Before Phase 2 commits deeply to Neo4j-specific features (native vector index, advanced Cypher graph algorithms, schema constraints), there is one open architectural decision worth a deliberate evaluation:

**SQLite as a lighter alternative.** Advantages: no Java/JVM dependency, single portable file, stdlib support (`sqlite3`), trivially embeddable. A graph-style schema can be implemented in SQL (nodes table, edges table, properties table). Disadvantages: no native vector index (would require a companion FAISS/Chroma instance), weaker concurrent write handling, no built-in shortest-path or graph projection operators.

**Decision gate:** evaluate SQLite before implementing Neo4j-specific Phase 2 features (e.g., graph projections for consolidation, native vector index queries). If the evaluation concludes SQLite cannot support the predict-observe-revise falsification query patterns without unacceptable complexity, Neo4j commitment deepens. If SQLite is sufficient for the core patterns, migration now is less disruptive than migration after Phase 2 feature build-out.

This is not a recommendation to migrate — it is a recommendation to make the decision explicitly rather than by default.

---

## Key Architecture Decisions Made

| Decision | Choice | Reason |
|---|---|---|
| Graph database | Neo4j | Persistent, queryable, supports complex relationship types |
| Vector index | nomic-embed (local) | No API cost; runs on-device |
| LLM calls | Anthropic API (cloud) + local Qwen fallback | Cost tiers; shutdown mode for budget protection |
| Web interface | Flask + SocketIO | Already built; chat + voice + audit dashboard |
| Phone tunnel | Tailscale | Private, encrypted, no port forwarding, secure |
| Avatar framework | Godot Engine | Already installed; near-zero overhead; transparent overlay |
| Sandbox | Deferred (browser window first) | Docker adds complexity; Windows games need native access |
| Computer vision | YOLO v8 + OpenCV (non-LLM) | Accurate bounding-box detection, not LLM coordinate guessing |
| Windows UI interaction | pywinauto (UI Automation) | Accessibility tree → named controls, not pixel coordinates |

---

## Research Foundation

Full findings in `docs/research-findings.md`. Key papers that shaped the architecture:

| Paper | Key contribution |
|---|---|
| Memory as Metabolism (2604.12034) | TRIAGE→CONSOLIDATE→AUDIT loop → Dream coordinator |
| ZenBrain (2604.23878) | 4-channel neuromodulator engine; Two-Factor KG edges |
| SCM (2604.20943) | Sleep-consolidated memory; NREM + REM phases → Dream NREM |
| D-MEM (2603.14597) | Dopamine-gated fast/slow routing → Drive + Neuromodulation |
| Fault-Tolerant Sandboxing (2512.12806) | Policy interception + snapshots → Hands policy layer |
| Theater of Mind (2604.08206) | Global Workspace Theory → Awareness bid-gating hub |
| Persistent Identity (2604.09588) | Multi-anchor identity; drift detection → Mirror-Self |
| Anatomy of Agentic Memory (2602.19320) | Memory taxonomy; backbone-dependency failure mode |
| H-MEM (2605.15701) | Hybrid tree+graph memory; validates graph+vector approach |

---

## What's Next

**Immediate (Phase 2 entry points — pick any):**
1. Expand Hands with computer-use actions (screenshot, mouse, keyboard, window management)
2. Add VisionSensor (YOLO + OpenCV) feeding VisualPercept into Sensory
3. Godot avatar — transparent overlay + WebSocket bridge to Python backend
4. Tailscale setup + phone access to existing web interface

**BrainLoop kernel hardening (Phase 2 — before deep Neo4j feature work):**
- Implement P0–P4 priority tier system in Awareness bid queue
- Refactor Dream into checkpointed stages (TRIAGE → CONSOLIDATE → AUDIT) with inter-stage yield and P1+ preemption
- Add Curiosity max queue depth (3 bids) with oldest-bid eviction
- Surface Awareness queue depth as a health signal in the coordinator dashboard
- Build mobile capture inbox queue — provisional staging before epistemic chain promotion
- Conduct SQLite evaluation before committing to Neo4j-specific Phase 2 features

**Later:**
- Wire `record_skill_practice` into coordinators that have measurable outcomes
- Share Drive instance between BrainLoop and Awareness (currently two separate instances)
- LLM-driven Claim extraction in Archivist (currently creates graph nodes but no claim text)
- Docker/VNC autonomous workspace
- Flutter/React Native mobile app with focus handoff
