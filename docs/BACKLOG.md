# Gopher-bot Backlog

**Maintained by:** Claude (Director)  
**Last updated:** 2026-05-26 (Cognition fixes committed 361da83; P-001 decay in-progress; Voyager-inspired items added)
**Rule:** Task numbers are retired. All items use descriptive names. Numbers caused duplicate collisions in Phase 2 and are not recoverable cleanly.

---

## Status Key

| Symbol | Meaning |
|---|---|
| ✅ | Done and committed |
| 🔄 | In progress right now |
| 📋 | Has a Codex prompt ready |
| ⬜ | Backlog — not started |
| 🔒 | Blocked by another item |

---

## Phase 1 — Complete

All T1–T67 complete. 683 tests passing. Formal closure doc: `docs/PHASE1_CLOSURE.md`.

---

## Phase 2 — Interface & Embodiment

### Done This Phase

| Item | Notes |
|---|---|
| ✅ Sensory schema (percepts.py) | VisualPercept + AuditoryPercept dataclasses, Sensory coordinator updated to accept percept dicts. 684 tests. |
| ✅ Hands computer-use expansion | pywinauto, pyautogui, mss, YOLO bbox clicking. pyproject.toml [vision] extras. Policy classifications: screenshot/mouse_move/get_window_list/focus_window = whitelist; clicks/type_text/key_press = greylist. |
| ✅ One-click launcher | start-bot.bat / stop-bot.bat. Neo4j auto-start via JRE detection (system Temurin 21 preferred over Cache Zulu 17). Polling loop for port 7687. Commit 4783671. |
| ✅ PySide6 World Map | QGraphicsScene live desktop map, monitor zones, window rooms, AvatarMarker with 300ms animation. WSClientThread → ws://localhost:5000/avatar-ws. Audit sidebar with turns.jsonl tail. |
| ✅ Discord bridge | interface/discord_bot.py. Channel filter, rate limiting, .txt attachment ingestion, process lock, reply chunking. Reads DISCORD_BOT_TOKEN and DISCORD_CHANNEL from config.py. |
| ✅ Discord image vision | Commit b2b683f. _describe_image() in Sensory via tier's sensory_model. image_attachments packet key: bridge → Sensory → VisualPercept.description. 13 new tests passing. |
| ✅ Archivist claim extraction | Commit 14d4b7a. turn log now stores message/response (capped 2000 chars). _extract_claims() via qwen2.5-3b-instruct at TIER_LOCAL. _default_claim_writer() links Claims to Source + LearningEpisode. 815 tests passing. |

### Ready / Next

| Item | Notes |
|---|---|
| ✅ Discord all-attachment support | Commit 73a6302. _read_all_text_attachments replaces txt-only handler. UTF-8 decode attempted on all non-image attachments; binary files get a note. Image-only message drop bug fixed. 824 tests. |
| ✅ visual_percept → Reason context | Commit 0fece9a. visual_percept.description wired into Reason system prompt. 828 tests. |
| ✅ Document ingestion to graph | Commit 0e12b68. Text attachments chunked and stored as external_content Observations. Image descriptions stored same way. Both retrievable by Memory via vector search across restarts. 842 tests. |
| ✅ API call timeouts | Commit 174f98e. 90s Reason, 30s Sensory, 20s Archivist. Prevents bot hang when LM Studio is degraded. 852 tests. |
| ✅ Two-lane memory retrieval | Commit f388c42. Recent episodic lane (last 6 source_type=observed exchanges) always surfaces alongside keyword-relevant lane. Fixes bot not seeing its own recent conversation history. |
| ✅ Semantic chunking | Commit d7b1584. Structure-aware split on markdown headers, numbered sections (§8.2), paragraph breaks. Header preserved in sub-chunks. Fixes section fragmentation in whitepaper ingestion. |
| ✅ VisionSensor: YOLO + OpenCV + EasyOCR | Commit 61f78ec. YOLO v8 nano objects, OpenCV motion, EasyOCR text → full VisualPercept. Memory.store_visual_observation() with source_type="perceived". Hands click_label + get_visible_elements. Reason gets element label list. MediaPipe (face/pose) deferred. |
| ✅ VLM semantic screen description | Commit 5ffac75. Optional LM Studio vision-language enrichment for stored visual observations: mechanical VisionSensor description remains live/fast; memory storage appends `Scene: ...` VLM prose only when VISION_VLM_MODEL is configured and available. 922 tests. |
| ✅ Configurable embedding model | Commit aebb114. `EMBEDDING_MODEL` in config.py overrides hardcoded default. Re-index warning comment. 6 new tests. 974 tests. |
| ✅ Local VLM image passthrough | Sensory base64-encodes Discord image attachments for local tiers and passes as `raw_images_for_reason`; Reason builds OpenAI-compatible `image_url` multimodal blocks. Cloud Anthropic description path unchanged. 989 tests. |
| ✅ Orientation clock | `_operational_context()` now prepends `Current time: <iso>` so the bot can answer time-aware questions. 991 tests. |
| ✅ Audio and video routing | Commit 2886532. Discord audio attachments (`.ogg`, `.mp3`, etc.) transcribed via OpenAI Whisper API into `AuditoryPercept.transcript` and promoted to `packet["message"]`. Video attachments processed via ffmpeg: keyframes described by VLM, audio transcribed. Graceful degradation if ffmpeg absent. 1000 tests. |
| ✅ Document parsing | Commit 40b1e87. PDF (pdfplumber), DOCX (python-docx), XLSX/XLS (openpyxl), PPTX (python-pptx), RTF (tag stripping). All parsers degrade gracefully if library absent. Unsupported binary formats receive clear "format not supported" note. 1012 tests. |
| ✅ On-demand screen capture + sensor self-awareness | Commit e98bf2a. Sensory detects screen-intent phrases and captures fresh screenshot via mss; routes through existing VLM pipeline (local multimodal or cloud description). Orientation `_operational_context()` now reports active sensors so bot's self-model is accurate. 1021 tests. |
| ✅ OmniParser + drag primitives | Commit f698d1e. sensors/omni_parser.py wraps OmniParser-v2.0 (Microsoft, GUI-trained). Hands gets locate_on_screen (whitelist), drag_to + drag_element (greylist). General foundation for chess, games, file drag, sliders — anything requiring drag input or on-demand element location. pywinauto covers native Windows apps via accessibility tree; OmniParser covers rendered/visual UIs (games, browsers). 1031 tests. |
| ⬜ AudioSensor | Silero VAD (gate) → Whisper (transcription) → YAMNet (sound class) → Librosa (prosody). Output → AuditoryPercept. |
| ⬜ Sensory pipeline decision | Decide: sequential (500ms tick) vs. event-driven (threshold interrupt → <100ms reflex). Event-driven chosen in principle; interrupt model for BrainLoop not yet designed. Needs a Codex task once decision is finalized. |
| ⬜ Godot avatar full implementation | Scaffold exists and connects to /avatar-ws. Full animation states: meditating (graph query), typing (code), pacing/napping (idle), startle (sensory anomaly). Humanized execution: avatar walks to app icon before action fires. |
| ⬜ PySide6 / Godot persona event schema | /persona event should be designed for dual consumers: Godot avatar AND PySide6 world map. Not just simple state strings — needs to carry attention focus, coordinator state, neuromodulator levels. |
| ⬜ Tailscale setup | Private mesh tunnel. Flask already binds 0.0.0.0. No code change needed for basic phone access to web interface. Operational task, not a Codex task. |
| ⬜ Hands self-verification loop | After any multi-step computer-use sequence: take screenshot, ask Reason "did this accomplish the goal?", feed errors back and retry. Voyager critic loop adapted for desktop automation. Foundation for reliable autonomous Hands operation. OmniParser locate_on_screen already available. |
| ⬜ Task decomposition for Hands | Before executing a multi-step Hands sequence, decompose into checkpointed sub-goals with individual success criteria. Failure at step N retries from N, not from 1. Pairs with self-verification loop. Voyager sub-goal pattern. |

---

## Phase 2 — Activity Model (Executive Function)

| Item | Notes |
|---|---|
| ✅ Activity model Part A — schema + recognition | Commit f475cc8. Activity node CRUD in graph.py, _detect_activity (FEN/reminder/task/conversation), check_scheduled_activities, BrainLoop 10s tick. 13 tests. 1042 passing (excl. live Neo4j suite). |
| ✅ Activity model Part B — coordinator wiring | Commit fa86dbc. Orientation injects Activity block, Hands patches last_action, Reason auto-records skill practice (game/learning), Memory boosts keywords from skill domains. Also extended VALID_SKILL_DOMAINS in graph.py (chess, computer_use). 10 tests. 1052 passing. |

---

## Phase 2 — Memory & Cognition

| Item | Notes |
|---|---|
| ✅ Archivist claim extraction | Done — commit 14d4b7a. |
| ✅ Observation/Inference separation (P-001 Refinement 1) | Commit 361da83. Reason source authority hierarchy (ORIENTATION wins), absolute reminder time parsing ("at 8:50 am" etc.), Discord proactive loop polls /proactive-messages endpoint, "perceived" in VALID_SOURCE_TYPES, _format_observation tags non-observed source types. 11 new tests. 1071 passing. |
| ✅ Confidence weights + decay (P-001 Refinement 2) | Commit 78b2dbb. last_confirmed_at on Observation nodes (equal to created_at at creation); decay_stale_observations() in graph.py lowers confidence 5%/NREM for nodes >14 days unconfirmed, floored at 0.05; Dream NREM wires decay, failure isolated. 5 new tests. 1076 passing. |
| ⬜ Organic node-type emergence | Dream CONSOLIDATE detects clusters of Beliefs without a name → flags for Wisdom. Wisdom proposes new node labels. Depends on: Archivist claim extraction wired first. |
| 🔒 Wisdom coordinator (temporal-epistemic) | Wisdom is distinct from Memory — it compares current Doctrines to prior Claims, identifies recurring correction patterns, names novel Belief clusters. Depends on: Archivist claim extraction. Weekly cadence or Dream AUDIT trigger. |
| ⬜ Drive instance sharing | BrainLoop and Awareness currently run separate Drive instances. Should share one to prevent budget tracking drift. |
| ⬜ SkillNode practice recording | Auto-wired by Activity model Part B for game/learning activities. Manual wiring for other coordinators deferred. |
| ⬜ SkillNode procedure storage | Extend SkillNode from label-only to storing executable procedure content. When bot succeeds at a verified multi-step Hands task, encode the procedure with a docstring. Retrieval via vector search. Reuse without re-reasoning from scratch. Voyager skill library pattern for desktop automation. Depends on: Hands self-verification loop (needs verified success signal). |

---

## Phase 2 — Model Intelligence

| Item | Notes |
|---|---|
| ⬜ Model evaluation & advisor | Background coordinator: runs test prompts against AVAILABLE_MODELS on slow cadence, records latency + basic quality signal per role, surfaces recommendations via bid system. Requires hardware probe at startup (VRAM/RAM) for local model viability. Depends on: AVAILABLE_MODELS (this task). |

---

## Phase 2 — BrainLoop Kernel Hardening

These are required before deep Phase 2 sensor work or the bid queue will degrade under load.

| Item | Notes |
|---|---|
| ⬜ P0–P4 bid priority tier system | P0=SAFETY (bypass queue), P1=CAPTURE (mobile/user input, preempts Dream), P2=HEALTH (Drive warnings), P3=INSIGHT (Pattern Monitor, Wisdom, Mirror-Self), P4=AMBIENT (Curiosity, Feeling probes, rate-limited, oldest-bid eviction). |
| ⬜ Dream checkpointing (interruptible) | Refactor Dream into TRIAGE → CONSOLIDATE → AUDIT as checkpointed stages. Yield + check for P1+ bids between stages. Resume from checkpoint rather than restart. Prevents long consolidation runs blocking mobile capture. |
| ⬜ Curiosity queue depth cap | Max 3 Curiosity bids in queue. Oldest evicted when cap reached. Stale questions are worse than no questions. |
| ⬜ Directed curriculum (Curiosity upgrade) | Replace undirected Curiosity bids with a curriculum agent that inspects SkillNode gaps and proposes targeted practice goals. "Attempted chess 5 times but mastery untracked — propose self-assessment" rather than random topic exploration. Voyager automatic curriculum pattern. Depends on: SkillNode procedure storage, P0–P4 bid tier system. |
| ⬜ Queue depth as health signal | Awareness surfaces P3/P4 backlog depth to coordinator dashboard. Drive factors persistent P4 backlog into tier decisions. |
| ⬜ Mobile capture inbox queue | Mobile input → provisional PortableCapture struct → inbox (not yet promoted to Source). Awareness surfaces inbox items at next desktop interaction for confirm/discard. On confirm: promoted to Source → Archivist pipeline. |

---

## Phase 2 — Mobile Bridge

| Item | Notes |
|---|---|
| ⬜ Mobile bridge (T74 in old numbering) | Flutter or React Native. Lightweight — no AI on phone. Streams sensory data (audio, camera → VisualPercept dict over Tailscale, not raw video). |
| ⬜ Phone percept schemas | LocationPercept (GPS, moving/still, speed), MotionPercept (accelerometer + gyro: walking/running/sitting/sleeping), ambient light. Feed alongside VisualPercept and AuditoryPercept. |
| ⬜ Focus handoff state machine | Tap "Call" → PC avatar exit → perception loop shifts to phone → avatar materializes on phone. Presence is singular, not duplicated. |

---

## Architecture Decision Gate

| Decision | Status | Notes |
|---|---|---|
| SQLite vs Neo4j | ⬜ Pending | Evaluate before implementing Neo4j-specific Phase 2 features (graph projections, native vector index). If SQLite can support predict-observe-revise query patterns without unacceptable complexity, migrate now. If not, commit to Neo4j. Make this explicit, not by default. |
| Sequential vs event-driven Sensory | ⬜ Pending | Leaning event-driven (<100ms reflex). BrainLoop interrupt model needs design before Codex task is written. |
| Persona event schema | ⬜ Pending | Design for dual consumers (Godot + PySide6) before implementing either side's consumption logic. |

---

## Deferred Indefinitely

| Item | Reason |
|---|---|
| WiFi CSI spatial sensing | Requires raw hardware CSI access, consumer routers don't expose it, needs multiple APs + specialized firmware. Worth revisiting if project matures. |
| Docker/VNC autonomous workspace | Docker can't reach real Windows desktop or Steam games. Replaced by: designated browser window + D:\gopher-bot\workspace\ as Gopher-bot's home. |
| Governed self-distillation | Design documented. No training pipeline. Far future. |
| Model evaluation framework | Provider discovery done. Benchmark-based switching is Phase 3+. |

---

## Test Suite Baseline

**1076 tests** (P-001 decay complete baseline — commits 361da83 + 78b2dbb). Full suite runs with:
```
pytest --basetemp .tmp/pytest-tmp -q
```
