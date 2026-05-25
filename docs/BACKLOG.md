# Gopher-bot Backlog

**Maintained by:** Claude (Director)  
**Last updated:** 2026-05-25 (Archivist/STT/TTS model overrides — 950 tests)
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
| ⬜ OmniParser UI element detection | Replace YOLO (COCO real-world classes) with OmniParser for GUI-aware element detection: buttons, icons, interactive regions. Complements EasyOCR (text) and VLM (semantic). Fills the click-target gap for non-text UI elements. |
| ⬜ AudioSensor | Silero VAD (gate) → Whisper (transcription) → YAMNet (sound class) → Librosa (prosody). Output → AuditoryPercept. |
| ⬜ Sensory pipeline decision | Decide: sequential (500ms tick) vs. event-driven (threshold interrupt → <100ms reflex). Event-driven chosen in principle; interrupt model for BrainLoop not yet designed. Needs a Codex task once decision is finalized. |
| ⬜ Godot avatar full implementation | Scaffold exists and connects to /avatar-ws. Full animation states: meditating (graph query), typing (code), pacing/napping (idle), startle (sensory anomaly). Humanized execution: avatar walks to app icon before action fires. |
| ⬜ PySide6 / Godot persona event schema | /persona event should be designed for dual consumers: Godot avatar AND PySide6 world map. Not just simple state strings — needs to carry attention focus, coordinator state, neuromodulator levels. |
| ⬜ Tailscale setup | Private mesh tunnel. Flask already binds 0.0.0.0. No code change needed for basic phone access to web interface. Operational task, not a Codex task. |

---

## Phase 2 — Memory & Cognition

| Item | Notes |
|---|---|
| ✅ Archivist claim extraction | Done — commit 14d4b7a. |
| ⬜ Observation/Inference separation (P-001 Refinement 1) | Add source_type: observed / inferred / proposed to Observation nodes. Memory coordinator tags every write. Pattern Monitor + Reason treat inferred nodes with lower default confidence. Proposal P-001 approved by Gopher. |
| ⬜ Confidence weights + decay (P-001 Refinement 2) | confidence float + last_confirmed_at on Observation nodes. Dream applies decay during idle. Pattern Monitor watches decaying clusters. |
| ⬜ Organic node-type emergence | Dream CONSOLIDATE detects clusters of Beliefs without a name → flags for Wisdom. Wisdom proposes new node labels. Depends on: Archivist claim extraction wired first. |
| 🔒 Wisdom coordinator (temporal-epistemic) | Wisdom is distinct from Memory — it compares current Doctrines to prior Claims, identifies recurring correction patterns, names novel Belief clusters. Depends on: Archivist claim extraction. Weekly cadence or Dream AUDIT trigger. |
| ⬜ Drive instance sharing | BrainLoop and Awareness currently run separate Drive instances. Should share one to prevent budget tracking drift. |
| ⬜ SkillNode practice recording | record_skill_practice() exists but isn't wired into coordinators that have measurable outcomes. Wire into Reason (at minimum) post-Phase 2 stabilization. |

---

## Phase 2 — BrainLoop Kernel Hardening

These are required before deep Phase 2 sensor work or the bid queue will degrade under load.

| Item | Notes |
|---|---|
| ⬜ P0–P4 bid priority tier system | P0=SAFETY (bypass queue), P1=CAPTURE (mobile/user input, preempts Dream), P2=HEALTH (Drive warnings), P3=INSIGHT (Pattern Monitor, Wisdom, Mirror-Self), P4=AMBIENT (Curiosity, Feeling probes, rate-limited, oldest-bid eviction). |
| ⬜ Dream checkpointing (interruptible) | Refactor Dream into TRIAGE → CONSOLIDATE → AUDIT as checkpointed stages. Yield + check for P1+ bids between stages. Resume from checkpoint rather than restart. Prevents long consolidation runs blocking mobile capture. |
| ⬜ Curiosity queue depth cap | Max 3 Curiosity bids in queue. Oldest evicted when cap reached. Stale questions are worse than no questions. |
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

**950 tests** (Archivist/STT/TTS model overrides baseline). Full suite runs with:
```
pytest --ignore=tests/test_graph.py -v
```
