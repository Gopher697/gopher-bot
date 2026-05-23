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
- **Auditable by design** — the Hands coordinator enforces an action whitelist/greylist/blacklist. Graph writes produce JSONL audit logs. The governance layer is human-readable and committed to the repo.

## What it is not

- Not a finished product. Phase 1 (coordinator runtime and governance substrate) is complete. Phase 2 (full world-model loop, avatar, mobile capture) is planned.
- Not a plug-and-play assistant. Setup requires Python, Neo4j, and API keys for at least one LLM provider.
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

- 441+ tests passing
- Coordinator runtime fully implemented
- Governance infrastructure in place (charter, commitments, registry, proposal mechanism)
- World-model graph schema versioned and migration-tracked
- Graph write audit logging active
- Model registry and provider fallback routing

**Phase 2 — Planned.** See [`docs/VISION.md`](docs/VISION.md) for the roadmap. Key targets: full predictive world-model loop, avatar, mobile capture bridge, governed self-distillation.

---

## Setup

### Prerequisites

- Python 3.11+
- [Neo4j Desktop](https://neo4j.com/download/) or a local Neo4j instance on `localhost:7687`
- API key for at least one supported LLM provider (Anthropic, OpenAI, or a local LM Studio instance)

### Installation

```powershell
git clone https://github.com/Gopher697/gopher-bot.git
cd gopher-bot
python -m pip install -r requirements.txt
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

Edit `world_models/config.py` with your Neo4j credentials and API key(s). **This file is gitignored and will never be committed.**

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
start-gopher-bot.bat
```

This starts Neo4j (if not already running), the Python backend on `http://localhost:5000`, and the world map interface.

---

## Tests

```powershell
python -m pytest --basetemp .tmp/pytest-tmp --ignore=tests/test_graph.py -q
```

`test_graph.py` requires a live Neo4j instance and is excluded from the default run. `test_vision_sensor.py` has a known pre-existing circular import — tracked in [`docs/PHASE1_CLOSURE.md`](docs/PHASE1_CLOSURE.md).

---

## Repository structure

```
coordinators/       coordinator implementations (foreground + background)
docs/               architecture docs, VISION, Phase 1 closure, whitepaper
interface/          Flask/SocketIO web interface and endpoints
logs/               build and action audit logs
proposals/          governance proposals (pending and resolved)
scripts/            healthcheck, migration runner, export utilities
sensors/            vision and audio sensor daemons
tests/              test suite
utils/              shared utilities (audit, registry, config validation)
world_models/       Neo4j graph, vector index, schema, model registry

AGENT_CHARTER.md        identity strata, authority tiers, proposal schema
AGENT_COMMITMENTS.md    governed slow-layer obligations
COORDINATOR_REGISTRY.md full coordinator role specifications
DEVELOPMENT_CHARTER.md  rules governing AI-assisted build sessions
```

---

## Research paper

[`docs/whitepaper.md`](docs/whitepaper.md) — *Gopher-bot: A Governed Neurosymbolic Personal AI Runtime* (v0.5)

The paper covers the theoretical motivation, architecture design, implementation status, known limitations, and open research questions. It is written to be read independently of the code.

---

## Governance

This project takes the governance of AI systems seriously as a design constraint, not an afterthought. The [`AGENT_CHARTER.md`](AGENT_CHARTER.md) defines identity strata, authority tiers, and the proposal mechanism by which the system can request changes to its own high-level structure. The [`DEVELOPMENT_CHARTER.md`](DEVELOPMENT_CHARTER.md) governs how AI-assisted build sessions interact with the codebase.

Build agents (Claude, Codex) are not runtime coordinators. They do not possess coordinator authority. This boundary is permanent and structural.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## License

AGPL-3.0 — see [`LICENSE`](LICENSE).
