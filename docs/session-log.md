# Session Log — Gopher-bot

This file is the project's persistent memory. Every significant decision, insight,
and architectural choice made during Claude sessions is written here immediately.
It is committed to the repo so it survives context resets and session ends.

---

## Session: 2026-05-25 — Full Sensory Intake + GitHub Hardening

**Resumed from:** Phase 1 complete, Phase 2 in progress. Last commit: embedding model override (974 tests).

### GitHub hardening completed
- Dependabot alerts, malware alerts, Secret Protection, and Push Protection all enabled.
- Community Standards gaps filled: Code of Conduct (Contributor Covenant via GitHub UI), issue templates (`bug_report.md`, `feature_request.md`), PR template with checklist.
- Repository published as v0.1.0 pre-release.
- Topics and description updated.
- VISION.md updated with Phase 3: Governed MCP Unification — gopher-bot as an installable MCP server where external agents request tools through the governance layer.

### Live bot test — issues found and fixed

**Image hallucination (root cause traced and fixed):**
The bot was hallucinating responses to images (e.g. describing a palm tree pixel art as a "Slack message screenshot"). Root cause: `_describe_image()` in Sensory returns `""` for local tiers (base_url set), producing the placeholder `(image attached; no description available at current tier)`. This placeholder was passed as plain text to Reason; qwen3.5 never received image bytes. Fix: Sensory now base64-encodes image bytes for local tiers and passes them as `raw_images_for_reason`; Reason builds OpenAI-compatible `image_url` multimodal content blocks. qwen3.5 (loaded with its vision projector) now actually sees the image. Cloud Anthropic description path unchanged.

**Orientation clock missing:**
Bot said "I don't have access to a real-time clock" despite `current_time` being injected into the packet on every turn by Awareness. `_operational_context()` in Orientation read process uptime (`session_age_seconds`) but not `current_time`. Fix: two lines added — prepend `Current time: <iso>` as the first item.

**Audio not transcribed:**
Discord voice messages were noted as binary files the bot couldn't process. Fix: Discord bridge now detects audio extensions, downloads bytes, and passes them as `audio_attachments`. Sensory transcribes via OpenAI Whisper API into `AuditoryPercept.transcript`, which existing Sensory logic promotes to `packet["message"]`. `.ogg` (Discord voice) remapped to `.webm` filename for Whisper API compatibility (both use Opus codec).

**Video not processed:**
Video attachments were unhandled. Fix: Discord bridge detects video extensions, passes bytes as `video_attachments`. Sensory calls ffmpeg via subprocess to extract keyframes (1/5s, max 4) and audio track; frames described by VLM, audio transcribed by Whisper. Graceful degradation printed and noted in visual_percept if ffmpeg not installed.

**Document formats not parsed:**
PDF, DOCX, XLSX, PPTX, RTF attachments were falling through to "(binary file -- content cannot be displayed)". Fix: `_extract_document_text()` added to Discord bridge, trying pdfplumber / python-docx / openpyxl / python-pptx / RTF tag stripping in sequence. All parsers degrade gracefully if library not installed.

### Architectural insight: context size
10K+ token context on first message traced to the Archivist processing old turn log files at startup and storing large observations. The vector retrieval mechanism itself is correct (capped at 12+6 items). Issue is the Archivist's startup behavior re-ingesting already-processed logs — tracked as a future fix.

### On-demand screen capture + sensor self-awareness (same session, continued)
Bot responded "I don't have access to your screen" despite mss and VisionSensor being installed. Two fixes:
- Sensory: `_SCREEN_INTENT_RE` detects phrases like "look at my screen" / "what do you see" and calls `_capture_screen()` (mss) to grab a fresh screenshot, routing it through the existing VLM pipeline (local multimodal or cloud Anthropic description path).
- Orientation: `_operational_context()` now reports active sensors (`screen-capture`, `screen-memory`) so the bot's self-model accurately reflects deployed capabilities instead of defaulting to base-model assumptions.
- Commit e98bf2a. 1021 tests. Also added `tests/__init__.py` to prevent third-party `tests` package import collision during full-suite collection.

### Timezone correction observed in live testing
Bot correctly reports UTC time but defaulted to EST (UTC-5) instead of EDT (UTC-4) when converting for a West Virginia user. User corrected it. Bot acknowledged DST and hedged correctly: "Whether I actually retain this depends on whether the correction makes it into the memory graph." Persistence to be verified at next session start.

### Chess session — live capability test
Fed the bot a rewritten chess rules document (chess_rules_for_gopher_bot.md — structured for the semantic chunker's ## header splitting). Bot absorbed and summarized correctly; demonstrated knowledge of openings, tactics, FEN, and game management.

Key findings:
- **Mouse drag not wired**: bot said "I'll click and drag" but nothing executed. Hands has click but no drag primitive. Falsely roleplayed moves until corrected.
- **Board state drift**: bot lost track of position across a long context. Providing FEN strings per turn resolved this as a user-side workaround.
- **VLM coordinate guessing rejected**: considered using VLM to return pixel coordinates for element location — rejected as mechanically unreliable (VLMs aren't designed for precise spatial localization).
- **Design decision**: general solution is OmniParser (Microsoft's GUI-trained model) for element detection → returns structured bboxes, no prompt engineering. Plus a `drag_to` primitive in Hands. Same infrastructure supports games, file managers, sliders — not chess-specific.
- **pywinauto for native apps**: accessibility tree gives exact coordinates without any vision for standard Windows apps. OmniParser is for rendered/visual UIs (games, browsers).
- Prompt written: `outputs/codex_omniparser_drag.md`.

### Test baseline
1021 tests passing. Suite: `pytest --basetemp .tmp/pytest-tmp -q`

---

## Session: 2026-05-21 (earlier today)

**Resumed from:** Task chain T1-T52 complete.
**Goal:** Commit T53 (tier system redesign), then plan Phase 2.

### Milestone: T1–T67 Complete
All 67 tasks committed. 683 tests passing. The coordinator fabric is complete.

### Correction: Computer-Use Philosophy
**Old assumption:** screenshot → LLM interprets coordinates → click (standard computer-use approach)
**Actual situation:** This is inaccurate LLM coordinate guessing. Gopher explicitly rejected it as a "lazy LLM solution."
**Correct approach:**
- **Games and dynamic canvases:** YOLO v8 detects elements, returns bounding boxes → click center of detected box. No LLM involved in coordinate selection.
- **Native Windows apps:** `pywinauto` walks the Windows UI Automation accessibility tree → activates named controls (e.g. `window.child_window(title="Start Game", control_type="Button").click()`). No pixel coordinates.

### Decision: Avatar Framework
**Chose:** Godot Engine
**Rejected:** Electron, Tauri, Qt/PySide6, WPF/WinForms, browser overlay
**Why:** Already installed on the machine. Can render a transparent borderless always-on-top window. Communicates with Python backend via local WebSocket. Near-zero GPU/RAM overhead. Supports high-quality 2D sprite animations.

### Decision: Phone Tunnel
**Chose:** Tailscale
**Rejected:** ngrok, Cloudflare Tunnel
**Why:** Private mesh network — only Gopher's devices. No public URL exposed. No port forwarding required. Bot has no auth layer; a public tunnel would be dangerous.
**Note:** Flask server already binds to `0.0.0.0` which is sufficient. Tailscale handles OS-level routing. No code change needed for basic phone access.

### Context: Sandbox / Autonomous Workspace
Docker/VNC initially seemed like the right sandbox for game interaction. This was wrong — Docker containers can't access the real Windows desktop or Steam games.
**Revised understanding:** Two separate concerns:
1. **Real desktop interaction** (games, apps on the actual monitor) → handled by Hands coordinator via pywinauto + YOLO, running natively on Windows. No sandbox.
2. **Autonomous workspace** (browser window, personal files folder) → `D:\gopher-bot\workspace\` as Gopher-bot's "home". Docker/VNC deferred indefinitely.

### Decision: Sensory Architecture — open question
Sequential (500ms tick) vs. event-driven reflex loop not yet decided. Leaning event-driven for <100ms avatar reactions to sensory anomalies, but BrainLoop interrupt model needs design review.

### Artifact Created: docs/VISION.md
Comprehensive project vision document written to `docs/VISION.md`. Covers all 16 coordinators, tier system, epistemic chain, full Phase 2 design, architecture decisions, research references.
**Why:** Phase 2 design context had been entirely lost from Claude's memory (never written to files). VISION.md ensures it can never be lost again.

### Artifact Created: session-logger skill
A general Claude skill (`session-logger.skill`) was created and installed. It activates at session start, reads existing log, writes decisions/insights/context immediately as they happen throughout a session. Solves the core problem of context loss across sessions.

---

## Session: 2026-05-21 (current session)

**Resumed from:** T1–T67 complete, VISION.md written, session-logger skill created.
**Goal:** Review Phase 2 Codex proposal, answer open questions, plan T68–T70.

### Proposal Under Review: Phase 2 Systemic Manifestation
A Codex/Antigravity proposal document submitted covering:
1. Sensory Contract (percepts.py + reflex threads)
2. Hands computer-use expansion (pywinauto, pyautogui, mss, YOLO bbox clicking)
3. WebSocket Persona Gateway for Godot
4. Mobile Bridge + Focus Handoff state machine

### Decision: Dependency Strategy
**Chose:** Optional `[vision]` extras block in `pyproject.toml`
**Why:** `torch`, `ultralytics`, `opencv-python`, `pywinauto`, `whisper` are heavy. The bot must be runnable without them for basic chat/reasoning. Vision/audio capabilities are an upgrade, not a requirement.
**Implementation:** `pip install -e ".[vision]"` to activate. `requirements.txt` stays lean for base install.

### Decision: Model Weights Caching
**Chose:** Local cache directory `D:\gopher-bot\models\` (gitignored)
**Why:** Don't download on every startup. Download-once via `scripts/download_models.py`.

### Decision: Tailscale / Flask Binding
Binding to `0.0.0.0` is sufficient. No code change needed.

### Decision: Reflex Loop / BrainLoop Interrupt
Approved. `threading.Event()` flag, checked between pipeline stages only. Never mid-stage.

### Decision: Policy Classification for New Hands Actions
- `screenshot`, `mouse_move`, `get_window_list`, `focus_window` → **whitelist**
- `left_click`, `right_click`, `double_click`, `click_element`, `click_bbox`, `type_text`, `key_press` → **greylist**

### Decision: T68 Scope Constraint
T68 (Sensory Contract) = **schema only**. `percepts.py` dataclasses + Sensory coordinator updated to accept percept dicts. NO Silero, NO mss, NO hardware. Those come in T72 (AudioSensor). Antigravity must not import heavy deps in T68.

### Decision: Launcher
**Chose:** `start.bat` + `stop.bat` on desktop
One double-click starts Neo4j + Python backend + Godot avatar exe in correct order.
One double-click stops everything cleanly.
User never touches a terminal to run Gopher-bot.
Added as task #68 in task system.

### MAJOR DECISION: Desktop App Architecture — The World Map
**The web interface is a placeholder, not the product.**

**Core vision:** The computer IS Gopher-bot's world. The app renders a live spatial map of the actual desktop — monitors as zones, open windows as rooms/places, the avatar as a character moving through them. When the AI focuses on a window, you see it walk there. When a new app opens, a new space appears. The AI has geography — places it goes often, places it's never been.

**Technology: PySide6 (Qt for Python)**
**Rejected:** Browser/web interface as primary UI (kept for remote/phone access only), Electron, Tauri
**Why PySide6:** Python-native, real Windows desktop app, no browser restrictions, infinite canvas support via QGraphicsScene, same ecosystem as rest of codebase.

**How the world map works:**
- `pywinauto` / `win32gui` enumerate all open windows with their exact positions and sizes on each monitor
- PySide6 QGraphicsScene renders a live scaled-down map — two monitors = two zones, windows = labeled rooms
- Godot avatar position in the overlay corresponds to AI's current focus/attention in the map
- Map updates live as windows open, close, move, resize
- AI can navigate by issuing `focus_window` actions — avatar walks there before the action fires

**Layout:**
- Main canvas: the world map (AI's territory, free and spatial)
- Separate panel: audit/coordinator dashboard (outside the map — a control room)
- Conversation area: one panel among many in the canvas, not the whole product
- The AI can create, move, resize, and close panels in its canvas via Hands actions
- Layout persists in the graph between sessions — AI wakes up with its space arranged as it left it

**Architecture:**
- Flask/SocketIO backend stays — it's the brain
- PySide6 app connects via WebSocket — it's the world
- Godot avatar overlays on top as transparent window, position reflects AI's attention
- Browser interface kept for Tailscale/phone remote access only

**Impact:** This is the defining feature of Gopher-bot as a persistent cognitive entity, not a chat tool. The spatial map makes the AI's presence and attention visible and real.

### Milestone: T68 Complete
percepts.py + Sensory update committed. 684 tests passing. start-bot.bat stub also created by Antigravity during its audit (stale path data fixed silently — acceptable for a bat file, not acceptable for governance files).

### Milestone: T69 Complete
Hands computer-use expansion committed. pyproject.toml updated with [vision] extras. hands_policy.py and hands.py updated with new actions per policy classifications decided earlier.

### Open Decisions
- Sequential vs. event-driven sensory pipeline
- /persona event schema should be designed for dual consumers: Godot avatar AND future PySide6 world map app (not just simple state strings)

### Design: Phone as Full Sensory Organ (not just camera)
VisionSensor currently captures PC screen via mss. Phone camera is a second ingestion path — same VisualPercept output, different source. The Sensory coordinator doesn't care which source filled the percept.

Phone provides far more than camera + mic. Full inventory of achievable sensors:
- **Camera (front + back)** → VisualPercept (already designed)
- **Microphone** → AuditoryPercept (already designed)
- **GPS/Location** → LocationPercept — where you are, moving/still, speed, direction. Enables context-switching: home vs. work vs. in-transit changes how Gopher-bot behaves
- **Accelerometer + Gyroscope** → MotionPercept — walking, running, sitting, sleeping. Don't interrupt with complex tasks while walking; run background processes while sleeping
- **Magnetometer** → compass direction facing
- **Ambient light sensor** → lighting conditions in environment (indoors/outdoors, time-of-day corroboration)
- **Proximity sensor** → something close to the phone
- **Bluetooth/WiFi signals** → nearby devices, rough indoor positioning

These feed into a LocationPercept and MotionPercept schema to be designed alongside T74 (mobile bridge).

### Deferred (Too Complex for Now): WiFi Spatial Sensing
WiFi CSI (Channel State Information) can detect human movement, body pose, even breathing through walls using multiple access points. Real technology — MIT and others have demonstrated it. But requires:
- Access to raw WiFi hardware CSI data (consumer routers don't expose this)
- Specialized firmware/drivers
- Multiple APs for triangulation
- Significant signal processing pipeline

Worth revisiting if the project matures to that level. For now: deferred indefinitely.

### Unresolved Design Question: Organic Node-Type Emergence
**The question:** Can the graph organically develop new node types and classifications for concepts nobody programmed in advance?

**Current state:**
- Neo4j is schemaless — properties and relationship types are already flexible, existing nodes can grow richer organically
- The epistemic chain (Claim → Belief → Principle → Doctrine) is the intended organic concept-formation path — raw observations solidify into persistent concepts through repetition and reinforcement
- BUT: Archivist claim extraction is still stubbed. Container nodes are created but no LLM-extracted claim text is written. The pipeline is hollow.
- AND: All node labels are hardcoded in Python. Nothing in the system currently decides to create a genuinely new node category.

**The gap:** The AI cannot yet say "this concept doesn't fit existing categories — I need a new type." The graph could hold it, but nothing proposes it.

**Where the solution probably lives:** Dream's CONSOLIDATE phase — recognizing clusters of related Beliefs that don't have a name yet and proposing new node labels. This is how the graph develops its own ontology rather than being permanently limited to human pre-programming.

**Dependencies:** Archivist claim extraction must be wired first (T-future), then Dream CONSOLIDATE extended to recognize novel clusters.

Tracked as task #71.

### Design Insight: Wisdom Should Be Its Own Coordinator
Wisdom was merged into Memory during early design as "just a mode of memory." This was wrong.

**What Wisdom actually is:** Temporal epistemic comparison — looking at what the system believed at time T, comparing it to what it believes now, and extracting the *shape* of that shift as something actionable. Not "I know more now" but "I was wrong in a specific way, and that pattern of being wrong tells me where I'm likely to be wrong again."

**Memory retrieves. Wisdom reflects across time.**

What Wisdom does that Memory cannot:
- Compare current Doctrines to the Claims that existed before they solidified — what wasn't seen then?
- Identify recurring patterns in corrections — how the system tends to be wrong, not just what changed
- Look at clusters of Beliefs that have all shifted in the same direction and name that movement (this IS the organic node-emergence mechanism — Dream clusters, Wisdom names)
- Take the long view on Goal nodes — which goals recur, which keep failing, what does the pattern mean?
- Feed insights back into Curiosity (new questions) and Memory (strengthen connections)

**Connection to organic node emergence (#71):** Wisdom is the coordinator that proposes new node labels. Dream CONSOLIDATE produces the raw clusters. Wisdom interprets the temporal arc and decides whether a cluster represents something genuinely new that needs a name.

**Cadence:** Slower than Dream — weekly or triggered by Dream AUDIT output.

Tracked as task #72. Depends on Archivist claim extraction being wired first.

### Milestone: T68 Complete — One-Click Launcher Working
start-bot.bat and stop-bot.bat committed and tested end-to-end:
- Neo4j Desktop auto-detected via HKLM registry wildcard search (installed at C:\Program Files\Neo4j Desktop 2\Neo4j Desktop.exe)
- Polling loop waits up to 60s for port 7687 (2s intervals) instead of fixed timeout
- Python backend starts in minimized window titled "Gopher-bot Backend"
- Godot avatar exe launched (Vulkan/RTX 4070 SUPER confirmed)
- Full sequence confirmed: Neo4j RUNNING → backend → avatar → "Gopher-bot is running."

**Updated (current session):** Neo4j auto-start now working. JRE found via PowerShell `Get-ChildItem -Recurse -Depth 8` in Cache. JAVA_HOME calculation moved outside parenthesized if-block (batch parse-time expansion bug) using goto labels. `cmd /c "...neo4j.bat start"` prevents neo4j.bat's internal `exit` from closing the launcher window. Neo4j Desktop path hardcoded as C:\Program Files\Neo4j Desktop 2\Neo4j Desktop.exe fallback. DB may still take >60s on cold start — user clicks Start in Desktop as fallback. Commits: 0cec18f.

**Updated (later in current session):** Added system JAVA_HOME priority check — Temurin 21 (or any system JDK) is preferred over Cache JRE (Zulu 17). Zulu 17 is too old for Neo4j 2026.04.0 (requires Java 21 / class file 65; Zulu 17 only supports class file 61). Fix uses flag variable `_USE_SYS_JAVA` to avoid `goto` inside nested parenthesized `if`-blocks (cmd.exe parse-time crash). User installing Temurin JDK 21 via Eclipse Adoptium. Commit: 4783671.

### Milestone: T69 Complete — PySide6 World Map Live
Built by Antigravity and debugged in current session:
- QGraphicsScene infinite canvas with monitor zones (QApplication.screens()) and window rooms (win32gui)
- AvatarMarker (green dot) with 300ms QPropertyAnimation position transitions
- WSClientThread background WebSocket → ws://localhost:5000/avatar-ws (same endpoint as Godot avatar)
- Docked sidebar: state/coordinator/focus/neuromodulator display + audit log tail (turns.jsonl, 5s refresh)
- Window rooms refresh every 2 seconds via win32gui.EnumWindows
- Bug fixed: refresh_windows was calling removeItem() on the coordinate tuple (x,y,w,h) instead of the QGraphicsItem objects — fixed with try/except per item using entry[0]/entry[1] index access
- All components confirmed live: backend ✅, world map ✅, Godot avatar connected to /avatar-ws ✅
