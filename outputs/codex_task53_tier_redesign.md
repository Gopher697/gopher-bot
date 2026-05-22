# Codex Task 53 — Tier System Redesign: Cost Hierarchy + Tier 0 + Shutdown Mode

## Context

The current tier system has three tiers (local=1, Haiku/Sonnet=2, Haiku/Opus=3) defined in
`coordinators/tier_config.py`, with a duplicate partial cost table in `coordinators/drive.py`.
Two gaps:

1. **No Tier 0**: The COORDINATOR_REGISTRY.md describes many coordinators as "Tier 0 — no LLM
   calls" but Tier 0 doesn't exist in `tier_config.py` or `assess_tier`. There's no formal
   way to mark a turn as deterministic.

2. **Drive.process() is not in the foreground pipeline**: Drive has a `process(packet)` method
   that computes budget state and writes `drive_budget_status` to the packet, but it's never
   called during `Awareness.synchronous_run`. So budget data never reaches the foreground packet,
   and there's no mechanism to cap tiers when the budget is near its ceiling.

This task fixes both gaps:
- Redesigns `tier_config.py` with Tier 0, named constants, unified cost estimates, and
  `apply_shutdown_cap()`
- Wires `Drive.process()` into `Awareness.synchronous_run` before `assess_tier` so budget
  state and shutdown_mode are available for tier selection
- Updates `Awareness.assess_tier` to apply the shutdown cap and add `tier_name` to the packet
- Cleans up the duplicate `TIER_COST_ESTIMATES` in `drive.py`

**Known limitation:** The foreground Drive instance (created inside Awareness) is separate from
BrainLoop's background Drive instance. They do not share budget state. The foreground Drive
accurately tracks foreground turn costs; background costs are tracked separately. Sharing the
instance via `bind_awareness` is a future enhancement.

---

## Security invariant — check before every commit

`world_models/config.py` is gitignored and contains Neo4j credentials and API keys.
Run `git status` before committing. If `world_models/config.py` appears, STOP — do not commit.

---

## Part 1: Redesign `coordinators/tier_config.py`

Replace the entire file with the following:

```python
from __future__ import annotations

from dataclasses import asdict, dataclass


# ---------------------------------------------------------------------------
# Tier names — used for logging and packet annotation
# ---------------------------------------------------------------------------

TIER_DETERMINISTIC = 0   # No LLM call — pure Python / deterministic response
TIER_LOCAL         = 1   # Local LLM (localhost; zero marginal cost)
TIER_STANDARD      = 2   # Cloud Haiku + Sonnet  (default)
TIER_ENHANCED      = 3   # Cloud Haiku + Opus    (high-stakes / complex)

DEFAULT_TIER = TIER_STANDARD

# In shutdown mode, tier is capped at this value.
SHUTDOWN_TIER = TIER_LOCAL

# Budget fraction that auto-triggers shutdown mode in Drive.
SHUTDOWN_BUDGET_FRACTION = 0.95

TIER_NAMES: dict[int, str] = {
    TIER_DETERMINISTIC: "deterministic",
    TIER_LOCAL:         "local",
    TIER_STANDARD:      "standard",
    TIER_ENHANCED:      "enhanced",
}

# Estimated USD cost per LLM call at each tier (used by Drive for budget tracking).
TIER_COST_ESTIMATES: dict[int, float] = {
    TIER_DETERMINISTIC: 0.0,
    TIER_LOCAL:         0.0,
    TIER_STANDARD:      0.01,
    TIER_ENHANCED:      0.10,
}


# ---------------------------------------------------------------------------
# TierConfig — model assignments per tier
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TierConfig:
    base_url: str | None        # None = Anthropic cloud; str = local OpenAI-compat endpoint
    sensory_model: str | None   # None for TIER_DETERMINISTIC (no LLM)
    reason_model: str | None    # None for TIER_DETERMINISTIC (no LLM)


TIERS: dict[int, TierConfig] = {
    TIER_DETERMINISTIC: TierConfig(
        base_url=None,
        sensory_model=None,
        reason_model=None,
    ),
    TIER_LOCAL: TierConfig(
        base_url="http://localhost:1234/v1",
        sensory_model="qwen2.5-3b-instruct",
        reason_model="qwen3.5",
    ),
    TIER_STANDARD: TierConfig(
        base_url=None,
        sensory_model="claude-3-5-haiku-20241022",
        reason_model="claude-sonnet-4-6",
    ),
    TIER_ENHANCED: TierConfig(
        base_url=None,
        sensory_model="claude-3-5-haiku-20241022",
        reason_model="claude-opus-4-6",
    ),
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_tier_config(tier: int) -> dict:
    """Return the TierConfig for the given tier as a plain dict."""
    try:
        tier_number = int(tier)
    except (TypeError, ValueError):
        tier_number = DEFAULT_TIER
    return asdict(TIERS.get(tier_number, TIERS[DEFAULT_TIER]))


def get_tier_name(tier: int) -> str:
    """Return the human-readable name for a tier number."""
    try:
        return TIER_NAMES.get(int(tier), "unknown")
    except (TypeError, ValueError):
        return "unknown"


def get_tier_cost_estimate(tier: int) -> float:
    """Return the estimated USD cost per LLM call at this tier."""
    try:
        return TIER_COST_ESTIMATES.get(int(tier), TIER_COST_ESTIMATES[DEFAULT_TIER])
    except (TypeError, ValueError):
        return TIER_COST_ESTIMATES[DEFAULT_TIER]


def apply_shutdown_cap(tier: int, shutdown_mode: bool) -> int:
    """
    If shutdown_mode is True, cap the tier at SHUTDOWN_TIER.

    This prevents expensive cloud LLM calls when the budget is near ceiling.
    If shutdown_mode is False, returns tier unchanged.
    """
    if not shutdown_mode:
        return int(tier)
    return min(int(tier), SHUTDOWN_TIER)
```

---

## Part 2: Update `coordinators/drive.py`

### Remove duplicate cost table and import from tier_config

Remove the line:
```python
TIER_COST_ESTIMATES = {1: 0.00, 2: 0.01, 3: 0.10}
```

Add import at the top of drive.py (with other imports):
```python
from coordinators.tier_config import SHUTDOWN_BUDGET_FRACTION, TIER_COST_ESTIMATES
```

Note: `SHUTDOWN_BUDGET_FRACTION` was defined in tier_config.py above. Remove any local
definition if it already exists in drive.py.

### Add `shutdown_mode` to `DriveState`

```python
@dataclass
class DriveState:
    ...
    shutdown_mode: bool = False   # True when budget_fraction >= SHUTDOWN_BUDGET_FRACTION
```

### Update `Drive.process(packet)` — add shutdown_mode

After computing `drive_budget_status`, add:

```python
budget_fraction = _budget_fraction(self.state)
self.state.shutdown_mode = budget_fraction >= SHUTDOWN_BUDGET_FRACTION

# Inject shutdown_mode into the packet so assess_tier can cap tier selection.
# Only set if not already set by the caller (allows external override).
if "shutdown_mode" not in packet:
    packet["shutdown_mode"] = self.state.shutdown_mode

# Add shutdown_mode to the budget status dict.
packet["drive_budget_status"]["shutdown_mode"] = self.state.shutdown_mode
packet["drive_budget_status"]["budget_fraction_at_shutdown"] = SHUTDOWN_BUDGET_FRACTION
```

Also update `DriveState.session_api_calls` default to include tier 0:

```python
session_api_calls: dict[int, int] = field(
    default_factory=lambda: {0: 0, 1: 0, 2: 0, 3: 0}
)
```

And update `record_api_call` to use `get_tier_cost_estimate` from tier_config:

```python
def record_api_call(self, tier: int, cost: float | None = None) -> None:
    tier = int(tier)
    self.state.session_api_calls.setdefault(tier, 0)
    self.state.session_api_calls[tier] += 1
    self.state.session_budget_used += (
        float(cost) if cost is not None else get_tier_cost_estimate(tier)
    )
    self._update_pending_budget_warning()
```

Add import for `get_tier_cost_estimate`:
```python
from coordinators.tier_config import SHUTDOWN_BUDGET_FRACTION, TIER_COST_ESTIMATES, get_tier_cost_estimate
```

---

## Part 3: Wire Drive into `coordinators/awareness.py`

### Import

```python
from coordinators.drive import Drive
```

### `Awareness.__init__` — add `drive` parameter

```python
def __init__(
    self,
    ...,
    drive: Drive | Coordinator | None = None,
) -> None:
    ...
    self.drive = drive or Drive()
```

### Update `synchronous_run` — call Drive before `assess_tier`

Currently `assess_tier` is the first call in the `try` block. Insert Drive before it:

```python
try:
    # --- Drive: budget state + shutdown_mode --------------------------------
    # Must run before assess_tier so shutdown_mode is in the packet before
    # tier selection. Non-fatal: pipeline continues if Drive fails.
    try:
        packet = self.drive.process(packet)
    except Exception:
        pass
    # -----------------------------------------------------------------------

    self.assess_tier(packet)
    packet = self.sensory.process(packet)
    ...
```

### Update `assess_tier`

```python
def assess_tier(self, packet: dict) -> dict:
    from coordinators.tier_config import (
        DEFAULT_TIER, TIER_ENHANCED, TIER_LOCAL, apply_shutdown_cap, get_tier_name,
    )

    if "tier" in packet:
        # Caller pre-set tier (e.g., test injection). Still apply shutdown cap.
        shutdown_mode = bool(packet.get("shutdown_mode"))
        packet["tier"] = apply_shutdown_cap(packet["tier"], shutdown_mode)
        packet["tier_name"] = get_tier_name(packet["tier"])
        return packet

    shutdown_mode = bool(packet.get("shutdown_mode"))

    if packet.get("high_stakes") is True:
        tier = TIER_ENHANCED
    else:
        message = str(packet.get("message", ""))
        if len(message) < 100 and "?" not in message:
            tier = TIER_LOCAL
        else:
            tier = DEFAULT_TIER

    tier = apply_shutdown_cap(tier, shutdown_mode)
    packet["tier"] = tier
    packet["tier_name"] = get_tier_name(tier)
    packet["shutdown_mode"] = shutdown_mode   # normalize to bool in packet
    return packet
```

---

## Part 4: Tests — `tests/test_tier_config.py` (new file)

All pure Python. No LLM calls, no disk, no network.

**Constants:**
- `test_tier_deterministic_is_zero` — `TIER_DETERMINISTIC == 0`
- `test_tier_local_is_one` — `TIER_LOCAL == 1`
- `test_tier_standard_is_two` — `TIER_STANDARD == 2`
- `test_tier_enhanced_is_three` — `TIER_ENHANCED == 3`
- `test_default_tier_is_standard` — `DEFAULT_TIER == TIER_STANDARD`
- `test_shutdown_tier_is_local` — `SHUTDOWN_TIER == TIER_LOCAL`
- `test_shutdown_budget_fraction_between_zero_and_one` — `0.0 < SHUTDOWN_BUDGET_FRACTION <= 1.0`

**`get_tier_name`:**
- `test_get_tier_name_deterministic` → `"deterministic"`
- `test_get_tier_name_local` → `"local"`
- `test_get_tier_name_standard` → `"standard"`
- `test_get_tier_name_enhanced` → `"enhanced"`
- `test_get_tier_name_unknown` — `get_tier_name(99)` → `"unknown"`
- `test_get_tier_name_invalid` — `get_tier_name("bad")` → `"unknown"` (no exception)

**`get_tier_cost_estimate`:**
- `test_cost_deterministic_is_zero` — `get_tier_cost_estimate(0) == 0.0`
- `test_cost_local_is_zero` — `get_tier_cost_estimate(1) == 0.0`
- `test_cost_standard_positive` — `get_tier_cost_estimate(2) > 0.0`
- `test_cost_enhanced_greater_than_standard` — cost(3) > cost(2)
- `test_cost_unknown_tier_returns_default` — `get_tier_cost_estimate(99)` returns default cost

**`apply_shutdown_cap`:**
- `test_no_cap_when_not_in_shutdown` — `apply_shutdown_cap(3, False) == 3`
- `test_cap_enhanced_to_local` — `apply_shutdown_cap(3, True) == SHUTDOWN_TIER`
- `test_cap_standard_to_local` — `apply_shutdown_cap(2, True) == SHUTDOWN_TIER`
- `test_local_unchanged_in_shutdown` — `apply_shutdown_cap(1, True) == 1`
- `test_deterministic_unchanged_in_shutdown` — `apply_shutdown_cap(0, True) == 0`

**`get_tier_config`:**
- `test_tier_0_has_none_models` — tier 0 config: `sensory_model is None`, `reason_model is None`
- `test_tier_1_has_local_url` — tier 1 config: `base_url` starts with "http://localhost"
- `test_tier_2_has_no_base_url` — tier 2 config: `base_url is None`
- `test_unknown_tier_returns_default` — `get_tier_config(99)` → same as `get_tier_config(DEFAULT_TIER)`

**Drive.process shutdown_mode:**
In `tests/test_drive.py` — add new tests:
- `test_shutdown_mode_false_when_budget_low` — budget 0.0 → `packet["shutdown_mode"] is False`
- `test_shutdown_mode_true_when_budget_at_ceiling` — set `state.session_budget_used =
  budget_ceiling * SHUTDOWN_BUDGET_FRACTION` → `packet["shutdown_mode"] is True`
- `test_shutdown_mode_not_overridden_if_already_set` — `packet["shutdown_mode"] = True` before
  `drive.process(packet)` with low budget → `packet["shutdown_mode"]` stays `True`
- `test_drive_budget_status_includes_shutdown_mode` — `packet["drive_budget_status"]["shutdown_mode"]`
  is present and is a bool

**`Awareness.assess_tier` with shutdown_mode (existing test file or test_awareness.py):**
- `test_assess_tier_caps_to_local_in_shutdown_mode` — `packet["shutdown_mode"] = True`,
  `packet["high_stakes"] = True`; after `assess_tier`, `packet["tier"] == TIER_LOCAL`
- `test_assess_tier_adds_tier_name` — after `assess_tier`, `"tier_name"` in packet
- `test_assess_tier_tier_name_matches_tier` — tier 2 → `tier_name == "standard"`

---

## Verification

```
pytest tests/test_tier_config.py --basetemp .tmp/pytest_codex_task53 -v
pytest tests/test_drive.py --basetemp .tmp/pytest_codex_task53 -v
pytest tests/test_awareness_orientation.py --basetemp .tmp/pytest_codex_task53 -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_codex_task53 -v
```

Confirm `world_models/config.py` is NOT staged:
```
git status
```

Commit:
```
git commit -m "feat: tier redesign — Tier 0 + named constants + shutdown mode + Drive foreground wiring (Task 53)"
```

---

## Summary of changes

| File | Change |
|---|---|
| `coordinators/tier_config.py` | Full redesign: Tier 0, named constants `TIER_DETERMINISTIC/LOCAL/STANDARD/ENHANCED`, `SHUTDOWN_TIER`, `SHUTDOWN_BUDGET_FRACTION`, `TIER_NAMES`, unified `TIER_COST_ESTIMATES`, new functions `get_tier_name`, `get_tier_cost_estimate`, `apply_shutdown_cap`; `TierConfig` fields made `str \| None` |
| `coordinators/drive.py` | Remove local `TIER_COST_ESTIMATES`; import from tier_config; add `shutdown_mode` to `DriveState`; add shutdown detection to `process()`; add tier 0 to `session_api_calls` default; use `get_tier_cost_estimate()` in `record_api_call()` |
| `coordinators/awareness.py` | Add `drive` param to `__init__`; wire `Drive.process()` before `assess_tier`; update `assess_tier` to call `apply_shutdown_cap()`, add `tier_name`, normalize `shutdown_mode` |
| `tests/test_tier_config.py` | New — ~25 pure-Python tests |
| `tests/test_drive.py` | Add 4 shutdown_mode tests |
| `tests/test_awareness_orientation.py` or similar | Add 3 assess_tier/shutdown_mode tests |
