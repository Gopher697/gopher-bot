# Security Policy

## Scope

Gopher-bot is an experimental local-first research prototype. It is designed to run on your own machine, communicating with local services (Neo4j, LM Studio) and remote LLM APIs (Anthropic, OpenAI).

## Credentials

**Never commit `world_models/config.py`.** This file contains your API keys and database credentials. It is gitignored by default. The example template is at `world_models/config.example.py`.

If you accidentally commit credentials:
1. Rotate the affected keys immediately at the provider dashboard.
2. Remove the file from git history (`git filter-repo` or BFG).
3. Force-push the cleaned history.

## Reporting vulnerabilities

This is a personal research project, not a production service. If you find a security issue — particularly anything involving credential handling, audit log bypass, or the governance/authority model — please open a GitHub issue marked **[SECURITY]** or email the maintainer directly.

## Known limitations

- The web interface (`interface/server.py`) runs on `localhost:5000` with no authentication. Do not expose it to a public network.
- The Hands coordinator enforces an action whitelist/greylist/blacklist, but this is Phase 1 scope. Policy-gated blocking of high-level graph writes is planned for Phase 2.
- The system is under active development and should not be trusted for unsupervised autonomous operation.
