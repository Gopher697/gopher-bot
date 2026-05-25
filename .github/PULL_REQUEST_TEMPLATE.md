## What this does
<!-- One paragraph summary of the change -->

## Why
<!-- Link to the issue this resolves, or explain the motivation -->

Closes #

## Checklist

- [ ] Issue opened and discussed before this PR (required for anything non-trivial)
- [ ] New coordinators implement the `Coordinator` base class from `coordinators/base.py`
- [ ] New coordinators registered in `COORDINATOR_REGISTRY.md` with role, tier, read paths, write paths, and behavioural rules
- [ ] New graph write functions call `audit_graph_write()` from `utils/graph_write_audit.py`
- [ ] Tests written and passing (`pytest --basetemp .tmp/pytest-tmp -q`)
- [ ] `world_models/config.py` is **not** staged (credentials must never be committed)
