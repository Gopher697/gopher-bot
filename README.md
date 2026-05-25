# Gopher-bot

**A local-first, governed personal AI runtime.**

Gopher-bot is an experimental neurosymbolic AI architecture exploring persistent identity, governed memory, and auditable behavior in a personal AI assistant. It is not a finished autonomous agent. It is a research prototype — built carefully, documented honestly, and published so others can study and extend the approach.

A companion research paper describing the architecture and design philosophy is in [`docs/whitepaper.md`](docs/whitepaper.md).

---

## What it is

Gopher-bot is a coordinator-based runtime that runs locally on your machine. Instead of a single large model acting as the "brain," it orchestrates a pipeline of specialized coordinators — each with a narrow responsibility, a defined authority tier, and auditable write paths to a persistent world model.

Key properties:

- **Persistent identity** — the system maintains a world-model graph (Neo4j) and vector index that survive restarts. It accumulates observations, beliefs, goals, and episodic memory over time.
- **Governed behavior** — every coordinator operates within an authority tier. Direct writes to high-level constructs (Principles, Doctrines) require a proposal mechanism. All graph writes are audit-logged.
- **Replaceable inference** — the LLM is an inference organ, not the identity. The model can be swapped; the accumulated world model and governance structure remain.
- **Model-agnostic** — declare your available models in `config.py` with a capability annotation and the tier system selects the best fit automatically. Supports Anthropic, OpenAI, DeepSeek, and local models via LM Studio.
- **Auditable by design** — the Hands coordinator enforces an action whitelist/greylist/blacklist. Graph writes produce JSONL audit logs. The governance layer is human-readable and committed to the repo.

## What it is not

- Not a finished product. Phase 1 (coordinator runtime and governance substrate) is complete. Phase 2 (embodiment, perception, memory refinement, full sensory intake) is actively in progress.
- Not a plug-and-play assistant. Setup requires Python, Neo4j, and at least one LLM provider (cloud API key or a local LM Studio instance).
- Not peer-reviewed research. This is a working prototype with a companion paper documenting design decisions and open questions.
- Not safe to run unsupervised. The system is under active development and should be treated as experimental.

---

## Architecture

The runtime has two layers:

**Foreground pipeline** (per-turn, synchronous):
```
Drive → Sensory → Memory → Orientation → Keeper → Mirror-User → Mirror-Self → Ethos → Reason → Hands → Voice → Feeling → Turn log
```

**Background runtime** (BrainLoop scheduler, cadence-based):
```
Feeling · Neuromodulation · Curiosity · Dream · Keeper · Archivist · Drive · Mirror-User · Mirror-Self · Pattern Monitor · Wisdom
```

The world model is a Neo4j graph with node types covering entities, observations, episodes, goals, beliefs, principles, doctrines, skills, and more. An epistemic chain (Source → Claim → Belief → Principle → Doctrine) governs how raw observations become durable knowledge.

See [`COORDINATOR_REGISTRY.md`](COORDINATOR_REGISTRY.md) for the full coordinator specification and [`AGENT_CHARTER.md`](AGENT_CHARTER.md) for the governance model.

---

## Status

**Phase 1 — Complete.** See [`docs/PHASE1_CLOSURE.md`](docs/PHASE1_CLOSURE.md) for the formal closure record.

**Phase 2 — In progress.** See [`docs/BACKLOG.md`](docs/BACKLOG.md) for current status.

### Shipped in Phase 2

- **Discord bridge** — channel-filtered message ingestion, image vision, attachment handling, rate limiting
- **VisionSensor** — YOLO v8 object detection, OpenCV motion detection, EasyOCR on-screen text; stores visual observations as memory
- **VLM semantic description** — optional local vision-language model enriches stored memory observations with scene understanding prose
- **PySide6 world map** — live desktop visualisation of monitor zones, window rooms, and avatar position
- **Hands computer-use expansion** — pywinauto/pyautogui screen interaction; `click_label` and `get_visible_elements` wired to VisionSensor
- **Archivist claim extraction** — background coordinator extracts durable factual claims from conversation turns via local LLM
- **Two-lane memory retrieval** — recent episodic lane always surfaces alongside keyword-relevant semantic lane
- **Semantic chunking** — structure-aware document splitting on markdown headers, numbered sections, paragraph breaks
- **Document ingestion to graph** — text and image attachments chunked and stored as retrievable external-content observations
- **AVAILABLE_MODELS** — declare available models with capability annotations; tier system selects best fit automatically
- **Configurable embedding model** — `EMBEDDING_MODEL` in `config.py` overrides the hardcoded default; re-index warning on change
- **Local VLM image passthrough** — Discord image attachments base64-encoded and sent as multimodal `image_url` blocks directly to the local vision-language model; cloud Anthropic vision path unchanged
- **Orientation clock** — current UTC timestamp surfaced in every Reason call so the bot can answer time-aware questions
- **Audio routing** — Discord voice messages and audio file attachments transcribed via OpenAI Whisper API and promoted to the foreground pipeline as `AuditoryPercept.transcript`
- **Video routing** — video attachments processed via ffmpeg: keyframes described by the VLM, audio track transcribed via Whisper; graceful degradation if ffmpeg absent
- **Document parsing** — PDF, DOCX, XLSX/XLS, PPTX, and RTF attachments parsed to extractable text before ingestion; binary formats that cannot be parsed receive a clear "format not supported" note

### Test baseline

1012 tests passing. Full suite:

```powershell
pytest --basetemp .tmp/pytest-tmp -q
```

---

## Setup

### Prerequisites

- Python 3.11+
- [Neo4j Desktop](https://neo4j.com/download/) or a local Neo4j instance on `localhost:7687`
- At least one of:
  - API key for a cloud LLM provider (Anthropic, OpenAI, or DeepSeek)
  - [LM Studio](https://lmstudio.ai/) running locally on `http://localhost:1234` with a chat model and an embedding model loaded

### Installation

```powershell
git clone https://github.com/Gopher697/gopher-bot.git
cd gopher-bot
python -m pip install -r requirements.txt
```

For the full vision stack (YOLO, OpenCV, EasyOCR):

```powershell
python -m pip install -e ".[vision]"
```

For development:

```powershell
python -m pip install -e ".[dev]"
```

### Configuration

Copy the example config and fill in your values:

```powershell
copy world_models\config.example.py world_models\config.py
```

Edit `world_models/config.py` with:

- `BOT_NAME` — what you want your instance called (propagates into system prompt, world model, and interface)
- Neo4j credentials
- API key(s) for your chosen providers
- `AVAILABLE_MODELS` — declare the models you have with capability annotations; the tier system picks the best fit for each role automatically
- `EMBEDDING_MODEL` — set once at initial setup to match the embedding model you have loaded in LM Studio; **do not change after data is stored** (changing dimensions breaks vector retrieval)

**`config.py` is gitignored and will never be committed.**

#### Example AVAILABLE_MODELS entry

```python
AVAILABLE_MODELS = [
    {"name": "claude-opus-4-6",          "provider": "anthropic",  "capability": "capable"},
    {"name": "claude-sonnet-4-6",         "provider": "anthropic",  "capability": "standard"},
    {"name": "claude-haiku-4-5-20251001", "provider": "anthropic",  "capability": "fast"},
    {"name": "qwen3.5",                   "provider": "lm_studio",  "capability": "local"},
    {"name": "qwen2.5-3b-instruct",       "provider": "lm_studio",  "capability": "local-fast"},
]
```

Capability values: `"capable"` (enhanced reasoning), `"standard"` (solid reasoning), `"fast"` (cloud sensory/cheap), `"local"` (local general), `"local-fast"` (local small/cheap).

### Database

Start your Neo4j instance, then run the baseline migration:

```powershell
python scripts/run_migrations.py
```

Verify the environment:

```powershell
python scripts/healthcheck.py
```

### Running

```powershell
start-bot.bat
```

This starts Neo4j (if not already running), the Python backend on `http://localhost:5000`, and the world map interface.

---

## Repository structure

```
coordinators/       coordinator implementations (foreground + background)
docs/               architecture docs, VISION, BACKLOG, Phase 1 closure, whitepaper
interface/          Flask/SocketIO web interface, Discord bridge, STT/TTS
logs/               build and action audit logs
proposals/          governance proposals (pending and resolved)
scripts/            healthcheck, migration runner, export utilities
sensors/            VisionSensor and AudioSensor daemons
tests/              test suite (1012 tests)
utils/              shared utilities (audit, registry, config validation)
world_models/       Neo4j graph, vector index, schema, model registry

AGENT_CHARTER.md        identity strata, authority tiers, proposal schema
AGENT_COMMITMENTS.md    governed slow-layer obligations
COORDINATOR_REGISTRY.md full coordinator role specifications
DEVELOPMENT_CHARTER.md  rules governing AI-assisted build sessions
SAFETY_CONTRACT.md      versioned runtime invariants the world model must always satisfy
```

---

## Research paper

[`docs/whitepaper.md`](docs/whitepaper.md) — *Gopher-bot: A Governed Neurosymbolic Personal AI Runtime* (v0.6)

The paper covers the theoretical motivation, architecture design, implementation status, known limitations, and open research questions. It is written to be read independently of the code.

---

## Governance

This project takes the governance of AI systems seriously as a design constraint, not an afterthought. The [`AGENT_CHARTER.md`](AGENT_CHARTER.md) defines identity strata, authority tiers, and the proposal mechanism by which the system can request changes to its own high-level structure. The [`SAFETY_CONTRACT.md`](SAFETY_CONTRACT.md) defines the structural invariants the world model graph must always satisfy, enforced at runtime by `scripts/verify_safety.py`. The [`DEVELOPMENT_CHARTER.md`](DEVELOPMENT_CHARTER.md) governs how AI-assisted build sessions interact with the codebase.

Build agents (Claude, Codex) are not runtime coordinators. They do not possess coordinator authority. This boundary is permanent and structural.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## License

AGPL-3.0 — see [`LICENSE`](LICENSE).
