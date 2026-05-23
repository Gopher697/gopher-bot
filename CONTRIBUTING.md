# Contributing

Gopher-bot is a personal research project. Contributions are welcome, but please read this first.

## What this project is

This is an experimental local-first AI runtime, not a general-purpose framework. Design decisions are made in service of a specific research agenda around governed memory, persistent identity, and auditable AI behavior. Contributions that fit that agenda are more likely to be accepted than general feature additions.

## Before opening a pull request

- Read [`AGENT_CHARTER.md`](AGENT_CHARTER.md) to understand the authority model and why the system is structured the way it is.
- Read [`docs/VISION.md`](docs/VISION.md) to understand where the project is going.
- Open an issue first for anything non-trivial. Describe what you want to change and why. This avoids wasted work.

## Code standards

- All coordinators must implement the `Coordinator` base class from `coordinators/base.py`.
- New coordinators must be registered in `COORDINATOR_REGISTRY.md` with role, tier, read paths, write paths, and behavioral rules.
- New graph write functions must call `audit_graph_write()` from `utils/graph_write_audit.py`.
- Tests are required. The suite uses `pytest`. Run with `pytest --basetemp .tmp/pytest-tmp -q`.
- Do not touch `world_models/config.py`. Credentials are never part of the codebase.

## Governance

Changes to `AGENT_CHARTER.md`, `AGENT_COMMITMENTS.md`, or the authority/tier model require explicit discussion and justification. These are not implementation details — they are structural commitments.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
