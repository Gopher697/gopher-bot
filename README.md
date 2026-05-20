# gopher-bot

Gopher-bot is the coordinator brain and local web interface for the persistent
agent architecture. This repo owns the bot-side runtime: coordinators, the
Flask/SocketIO interface, world-model integration, governance docs, proposals,
and bot tests.

The standalone Workbench MCP server lives in `D:\gopher-workbench`.

## Setup

Install runtime dependencies:

```powershell
python -m pip install -r requirements.txt
```

For editable development:

```powershell
python -m pip install -e ".[dev]"
```

Run the bot interface:

```powershell
python interface/server.py
```

Run tests:

```powershell
python -m pytest
```

## Main Paths

- `coordinators\` — Awareness, BrainLoop, Memory, Reason, Voice, and background coordinators.
- `interface\` — local web interface and voice/text endpoints.
- `world_models\` — graph and vector-index integration.
- `tests\` — bot/coordinator tests.
- `AGENT_CHARTER.md`, `AGENT_COMMITMENTS.md`, `COORDINATOR_REGISTRY.md` — governance layer.
- `proposals\` and `logs\` — proposal and build/runtime audit records.
