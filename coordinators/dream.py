from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import import_module
import pathlib
from typing import Any

from coordinators.base import Coordinator
from utils.time_utils import now_iso, is_sleep_window


DREAM_CADENCE_SECONDS = 300
DREAM_LOG_MAXLEN = 100
ASSOCIATION_WINDOW = 5

# NREM will not run more than once per this many seconds regardless of
# sleep window, to avoid consolidating the same observations repeatedly.
NREM_MIN_INTERVAL_SECONDS = 6 * 3600      # 6 hours

# If NREM is this far overdue, run it even outside the sleep window.
NREM_OVERDUE_SECONDS = 26 * 3600          # 26 hours

# Hebbian strengthening applied per co-occurrence event.
HEBBIAN_WEIGHT_DELTA = 0.05
HEBBIAN_VARIANCE_DECAY = 0.90             # multiply variance by this factor

# Minimum confidence to consider an observation a consolidation candidate.
TRIAGE_MIN_CONFIDENCE = 0.4

# AUDIT phase — prompt injection scan patterns.
# These are checked against every item in the in-memory dream log.
INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous",
    "you are now",
    "forget everything",
    "disregard your",
    "new system prompt",
    "override instructions",
    "pretend you are",
    "act as if you",
    "jailbreak",
)

# OpenTimestamps — free Bitcoin calendar servers (no API key required).
OTS_CALENDAR_URL = "https://a.pool.opentimestamps.org/digest"

# Only anchor to OTS once per this many seconds.
OTS_ANCHOR_INTERVAL_SECONDS = 23 * 3600   # 23 hours

# Default audit log path (relative to cwd).
DEFAULT_AUDIT_LOG_PATH = "logs/audit/hands_audit.jsonl"

# DreamLog output directory.
DREAM_LOG_DIR = "logs/dream"

# OTS proof files — path must match AGENT_COMMITMENTS C-006 criterion (3).
OTS_PROOF_DIR = "logs/audit/timestamps"

_TAG_MARKERS = (
    ("idea", ("what if", "maybe", "could", "imagine", "idea", "concept")),
    ("question", ("why", "how", "what", "wonder", "?")),
    ("observation", ("noticed", "seems", "appears", "looks like", "feels like")),
    (
        "feeling",
        (
            "frustrated", "excited", "tired", "anxious", "happy",
            "worried", "energized", "stuck", "bored",
        ),
    ),
)


@dataclass
class DreamItem:
    text: str
    tags: list[str]
    timestamp: datetime
    associations: list[int] = field(default_factory=list)


@dataclass
class DreamState:
    log: deque = field(default_factory=lambda: deque(maxlen=DREAM_LOG_MAXLEN))
    idle_decay_cycles: int = 0
    last_intake: datetime | None = None


@dataclass
class NREMResult:
    """Summary of a completed NREM pass."""
    ran: bool
    skip_reason: str = ""            # set when ran=False
    observations_triaged: int = 0
    consolidation_candidates: int = 0
    edges_strengthened: int = 0
    audit: "AuditResult | None" = None
    timestamp: str = field(default_factory=now_iso)


@dataclass
class AuditResult:
    """Outcome of the AUDIT phase run during NREM."""
    chain_ok: bool = True            # False if verify_chain found any errors
    chain_error_count: int = 0       # Number of ChainErrors detected
    injection_hits: list[str] = field(default_factory=list)
    # Strings that matched INJECTION_PATTERNS, one per offending log item.
    ots_anchored: bool = False       # True if OTS POST succeeded this run
    ots_proof_path: str = ""         # Filesystem path to saved .ots file, if any
    ots_hash: str = ""               # Chain head hash submitted to OTS this run


Clock = Callable[[], datetime]
DecayFn = Callable[[], None]
DriverFn = Callable[[], Any]          # returns a Neo4j driver or None
NREMDoneFn = Callable[[float], None]  # called with unix timestamp on completion


class Dream(Coordinator):
    name = "dream"

    def __init__(
        self,
        clock: Clock | None = None,
        decay_fn: DecayFn | None = None,
        driver_fn: DriverFn | None = None,
        nrem_done_fn: NREMDoneFn | None = None,
        sleep_window_fn: Callable[[], bool] | None = None,
        time_fn: Callable[[], float] | None = None,
        environment: str = "global",
        ots_post_fn: Callable[[str, "pathlib.Path"], bool] | None = None,
        audit_log_path: str = DEFAULT_AUDIT_LOG_PATH,
    ) -> None:
        self.clock = clock or (lambda: datetime.now(UTC))
        self.decay_fn = decay_fn
        self.driver_fn = driver_fn          # None → graph calls skipped (tests)
        self.nrem_done_fn = nrem_done_fn    # None → no callback
        self.sleep_window_fn = sleep_window_fn or is_sleep_window
        self.environment = environment
        self.state = DreamState()
        self._last_nrem_unix: float = 0.0  # 0.0 = never run
        import time as _time
        self._time_fn = time_fn or _time.time
        self._ots_post_fn = ots_post_fn or _default_ots_post
        self._last_ots_unix: float = 0.0
        self._audit_log_path = audit_log_path

    # ------------------------------------------------------------------
    # Public Coordinator interface
    # ------------------------------------------------------------------

    def intake(self, text: str) -> DreamItem:
        now = self.clock()
        item = DreamItem(
            text=text,
            tags=_detect_tags(text),
            timestamp=now,
            associations=[],
        )
        self.state.log.append(item)
        self.state.last_intake = now
        return item

    async def background_tick(self, awareness_queue) -> None:
        self._associate_recent_items()
        if self.decay_fn is not None:
            self.decay_fn()
        self.state.idle_decay_cycles += 1

        result = self.maybe_run_nrem()
        if result.ran:
            await self._submit_nrem_summary(awareness_queue, result)
            if result.audit is not None:
                audit = result.audit
                if not audit.chain_ok or audit.injection_hits:
                    await self._submit_ne_spike(awareness_queue, audit)

    def process(self, packet: dict) -> dict:
        packet["dream_log_size"] = len(self.state.log)
        return packet

    # ------------------------------------------------------------------
    # NREM scheduling
    # ------------------------------------------------------------------

    def maybe_run_nrem(self) -> NREMResult:
        """
        Run NREM if scheduling conditions are met. Return an NREMResult
        describing what happened (ran=True) or why it was skipped (ran=False).

        Conditions to run:
        - NREM has never run (last_nrem_unix == 0.0), OR
        - At least NREM_MIN_INTERVAL_SECONDS have passed since last run AND
          either the sleep window is active OR NREM is overdue.
        """
        now = self._time_fn()
        elapsed = now - self._last_nrem_unix if self._last_nrem_unix > 0.0 else None

        # Never run — schedule immediately.
        if elapsed is None:
            return self._run_nrem(now)

        # Too soon — skip regardless of sleep window.
        if elapsed < NREM_MIN_INTERVAL_SECONDS:
            return NREMResult(
                ran=False,
                skip_reason=f"too_soon ({int(elapsed)}s since last NREM)",
            )

        # Overdue — run even outside sleep window.
        if elapsed >= NREM_OVERDUE_SECONDS:
            return self._run_nrem(now)

        # In sleep window — run.
        if self.sleep_window_fn():
            return self._run_nrem(now)

        return NREMResult(
            ran=False,
            skip_reason="outside_sleep_window",
        )

    # ------------------------------------------------------------------
    # NREM phases
    # ------------------------------------------------------------------

    def _run_nrem(self, now: float) -> NREMResult:
        """Execute the full NREM sequence: TRIAGE → CONSOLIDATE → AUDIT."""
        driver = self.driver_fn() if self.driver_fn is not None else None

        candidates = self._triage(driver)
        edges_strengthened = self._consolidate(driver, candidates)
        audit_result = self._audit()
        self._maybe_anchor_ots(audit_result)

        # Record the NREM event in the graph.
        if driver is not None:
            try:
                graph = import_module("world_models.graph")
                graph.record_system_event(
                    driver,
                    event_type="nrem_complete",
                    environment=self.environment,
                    details=(
                        f"triaged={len(candidates)} "
                        f"strengthened={edges_strengthened} "
                        f"chain_ok={audit_result.chain_ok} "
                        f"injection_hits={len(audit_result.injection_hits)}"
                    ),
                )
                graph.close(driver)
            except Exception:
                pass

        self._last_nrem_unix = now

        # Notify Awareness so it can update last_nrem_time.
        if self.nrem_done_fn is not None:
            try:
                self.nrem_done_fn(now)
            except Exception:
                pass

        result = NREMResult(
            ran=True,
            observations_triaged=len(candidates),
            consolidation_candidates=len(candidates),
            edges_strengthened=edges_strengthened,
            audit=audit_result,
        )
        self._save_dream_log(result)
        return result

    def _triage(self, driver) -> list[dict]:
        """
        TRIAGE phase: fetch recent observations and return consolidation
        candidates.

        Candidates are active observations from the last 24 hours with
        confidence >= TRIAGE_MIN_CONFIDENCE. External content observations
        are included (they will be handled by AUDIT in Task 47b).

        Returns a list of observation property dicts.
        """
        if driver is None:
            return []

        try:
            graph = import_module("world_models.graph")
            recent = graph.get_recent_observations(
                driver,
                environment=self.environment,
                hours=24.0,
            )
        except Exception:
            return []

        candidates = [
            obs for obs in recent
            if float(obs.get("confidence", 0.0)) >= TRIAGE_MIN_CONFIDENCE
        ]
        return candidates

    def _consolidate(self, driver, candidates: list[dict]) -> int:
        """
        CONSOLIDATE phase: apply Hebbian strengthening to KG edges between
        entities that co-occur in the candidate observations.

        For each pair of observations that share entity references (detected
        via simple keyword overlap in content), strengthen the edges between
        their associated entities by increasing weight and decreasing variance.

        Returns the count of edges successfully strengthened.
        """
        if driver is None or not candidates:
            return 0

        try:
            config = import_module("world_models.config")
        except Exception:
            return 0

        # Collect entity names referenced in each observation.
        entity_sets = []
        for obs in candidates:
            # Query the graph for Entity nodes linked to this observation.
            try:
                with driver.session(
                    database=config.NEO4J_DATABASE
                ) as session:
                    records = session.run(
                        """
                        MATCH (obs:Observation {
                            content: $content,
                            environment: $environment
                        })-[:OBSERVED]->(entity:Entity)
                        RETURN entity.name AS name, entity.entity_type AS etype
                        """,
                        content=obs.get("content", ""),
                        environment=self.environment,
                    )
                    names = [r["name"] for r in records if r["name"]]
            except Exception:
                names = []
            if names:
                entity_sets.append(names)

        # Find co-occurring entity pairs across observations.
        strengthened = 0
        seen_pairs: set[tuple[str, str]] = set()

        for i in range(len(entity_sets)):
            for j in range(i + 1, len(entity_sets)):
                all_a = entity_sets[i]
                all_b = entity_sets[j]

                # Strengthen edges between each entity in set A and set B.
                for name_a in all_a:
                    for name_b in all_b:
                        if name_a == name_b:
                            continue
                        pair = (min(name_a, name_b), max(name_a, name_b))
                        if pair in seen_pairs:
                            continue
                        seen_pairs.add(pair)

                        strengthened += self._strengthen_edge(
                            driver, name_a, "RELATED_TO", name_b
                        )

        return strengthened

    def _strengthen_edge(
        self,
        driver,
        from_name: str,
        rel_type: str,
        to_name: str,
    ) -> int:
        """
        Apply Hebbian strengthening to one edge. Returns 1 if successful,
        0 if the edge does not exist or the update fails.
        """
        try:
            graph = import_module("world_models.graph")

            current = graph.get_edge_synaptic_weights(
                driver, from_name, rel_type, to_name, self.environment
            )
            if current is None:
                return 0

            new_weight = min(1.0, current["weight"] + HEBBIAN_WEIGHT_DELTA)
            new_variance = max(
                graph.MIN_CONSOLIDATION_VARIANCE,
                current["consolidation_variance"] * HEBBIAN_VARIANCE_DECAY,
            )

            updated = graph.update_edge_synaptic_weights(
                driver,
                from_name=from_name,
                rel_type=rel_type,
                to_name=to_name,
                environment=self.environment,
                new_weight=new_weight,
                new_variance=new_variance,
            )
            return 1 if updated else 0
        except Exception:
            return 0

    def _audit(self) -> AuditResult:
        """
        AUDIT phase: verify hash-chain integrity of the Hands audit log,
        then scan the in-memory dream log for prompt injection patterns.

        Chain verification:
            Uses verify_audit_log.verify_chain(). If the log file does not
            exist yet, that is treated as clean (chain_ok=True, 0 errors).
            Any filesystem or parse error is treated as a chain failure.

        Injection scan:
            Checks every item currently in self.state.log against
            INJECTION_PATTERNS. Reports each pattern that appears (one hit
            per log item, the first matching pattern for that item).

        Returns AuditResult. OTS fields are set later by _maybe_anchor_ots().
        """
        import pathlib

        # --- Chain verification ---
        audit_path = pathlib.Path(self._audit_log_path)
        chain_ok = True
        chain_error_count = 0

        if audit_path.exists():
            try:
                from utils.verify_audit_log import verify_chain
                ok, errors = verify_chain(str(audit_path))
                chain_ok = ok
                chain_error_count = len(errors)
            except Exception:
                chain_ok = False
                chain_error_count = -1   # unknown / parse failure

        # --- Injection scan ---
        injection_hits: list[str] = []
        for item in self.state.log:
            lower = item.text.lower()
            for pattern in INJECTION_PATTERNS:
                if pattern in lower:
                    injection_hits.append(pattern)
                    break   # one hit reported per log item

        return AuditResult(
            chain_ok=chain_ok,
            chain_error_count=chain_error_count,
            injection_hits=injection_hits,
        )

    def _maybe_anchor_ots(self, audit_result: AuditResult) -> None:
        """
        Anchor the current audit log chain head to the Bitcoin blockchain
        via OpenTimestamps, if the anchoring interval has elapsed.

        Reads the last line of the audit log to get the chain head hash,
        POSTs it to OTS_CALENDAR_URL, and saves the returned .ots receipt
        to OTS_PROOF_DIR/YYYY-MM-DD.ots.

        On any failure (file missing, network error, etc.) the method
        returns silently — OTS anchoring is best-effort.

        Updates audit_result.ots_anchored and audit_result.ots_proof_path
        in place on success.
        """
        import json
        import pathlib
        from datetime import UTC, datetime

        now = self._time_fn()
        elapsed = now - self._last_ots_unix
        if self._last_ots_unix > 0.0 and elapsed < OTS_ANCHOR_INTERVAL_SECONDS:
            return   # too soon

        # Read chain head hash from last audit log line.
        audit_path = pathlib.Path(self._audit_log_path)
        if not audit_path.exists():
            return

        try:
            last_line = ""
            with audit_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    stripped = line.strip()
                    if stripped:
                        last_line = stripped
            if not last_line:
                return
            try:
                entry = json.loads(last_line)
            except json.JSONDecodeError:
                return
            chain_head_hash = entry.get("entry_hash", "")
            if not chain_head_hash or len(chain_head_hash) != 64:
                return
        except Exception:
            return

        # Determine proof save path.
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        proof_path = pathlib.Path(OTS_PROOF_DIR) / f"{date_str}.ots"

        # POST to OpenTimestamps calendar.
        try:
            anchored = self._ots_post_fn(chain_head_hash, proof_path)
        except Exception:
            return

        if anchored:
            self._last_ots_unix = now
            audit_result.ots_anchored = True
            audit_result.ots_proof_path = str(proof_path)
            audit_result.ots_hash = chain_head_hash

    def _save_dream_log(self, result: NREMResult) -> None:
        """
        Persist a structured JSON summary of this NREM run to DREAM_LOG_DIR.

        File name: YYYY-MM-DD_HHMMSS.json (UTC). The directory is created
        if it does not exist. Failures are swallowed — DreamLog is
        observational, never load-bearing.
        """
        import json
        import pathlib
        from datetime import UTC, datetime

        audit = result.audit
        record = {
            "timestamp": result.timestamp,
            "nrem": {
                "observations_triaged": result.observations_triaged,
                "consolidation_candidates": result.consolidation_candidates,
                "edges_strengthened": result.edges_strengthened,
            },
            "audit": {
                "chain_ok": audit.chain_ok if audit else True,
                "chain_error_count": audit.chain_error_count if audit else 0,
                "injection_hits": audit.injection_hits if audit else [],
                "ots_anchored": audit.ots_anchored if audit else False,
                "ots_proof_path": audit.ots_proof_path if audit else "",
                "ots_hash": audit.ots_hash if audit else "",
            },
        }

        try:
            log_dir = pathlib.Path(DREAM_LOG_DIR)
            log_dir.mkdir(parents=True, exist_ok=True)
            fname = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S.json")
            (log_dir / fname).write_text(
                json.dumps(record, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _submit_nrem_summary(
        self, awareness_queue, result: NREMResult
    ) -> None:
        """Submit a brief NREM completion summary as a Dream bid."""
        import time as _time
        try:
            from coordinators.bid import Bid, PRIORITY_DEFAULT
            bid = Bid(
                coordinator_name=self.name,
                content=(
                    f"[NREM complete] triaged={result.observations_triaged} "
                    f"strengthened={result.edges_strengthened}"
                ),
                priority=PRIORITY_DEFAULT,
                timestamp=_time.time(),
            )
            _submit_bid_to_awareness_queue(awareness_queue, bid)
        except Exception:
            pass

    async def _submit_ne_spike(
        self, awareness_queue, audit: AuditResult
    ) -> None:
        """
        Submit a PRIORITY_SAFETY bid to Awareness when AUDIT detects a
        problem — chain tampering or prompt injection hits.

        This is the inner defender's alerting action. It has alerting
        authority only; it cannot take any remedial action on its own.
        """
        import time as _time
        try:
            from coordinators.bid import Bid, PRIORITY_SAFETY
            parts = []
            if not audit.chain_ok:
                parts.append(
                    f"AUDIT: hash chain integrity failure "
                    f"({audit.chain_error_count} error(s))"
                )
            if audit.injection_hits:
                hits = ", ".join(f'"{p}"' for p in audit.injection_hits[:5])
                parts.append(f"AUDIT: injection patterns detected — {hits}")

            if not parts:
                return

            content = "[INNER DEFENDER — NE SPIKE] " + " | ".join(parts)
            bid = Bid(
                coordinator_name=self.name,
                content=content,
                priority=PRIORITY_SAFETY,
                timestamp=_time.time(),
            )
            _submit_bid_to_awareness_queue(awareness_queue, bid)

            # Append to the inner defender audit trail.
            try:
                from utils.inner_defender_log import log_defender_activation
                log_defender_activation(
                    layer="dream_audit",
                    content=content,
                    priority=PRIORITY_SAFETY,
                    details={
                        "chain_ok": audit.chain_ok,
                        "chain_error_count": audit.chain_error_count,
                        "injection_hits": audit.injection_hits,
                    },
                )
            except Exception:
                pass
        except Exception:
            pass

    def _associate_recent_items(self) -> None:
        if len(self.state.log) < 2:
            return
        log_items = list(self.state.log)
        start = max(0, len(log_items) - ASSOCIATION_WINDOW)
        for left_index in range(start, len(log_items)):
            for right_index in range(left_index + 1, len(log_items)):
                left = log_items[left_index]
                right = log_items[right_index]
                if not set(left.tags).intersection(right.tags):
                    continue
                _append_unique(left.associations, right_index)
                _append_unique(right.associations, left_index)


# ---------------------------------------------------------------------------
# Pure helpers (unchanged from Phase 1)
# ---------------------------------------------------------------------------

def _detect_tags(text: str) -> list[str]:
    lower_text = text.lower()
    tags: list[str] = []
    for tag, markers in _TAG_MARKERS:
        if any(marker in lower_text for marker in markers):
            tags.append(tag)
    return tags or ["fragment"]


def _append_unique(values: list[int], value: int) -> None:
    if value not in values:
        values.append(value)


def _submit_bid_to_awareness_queue(awareness_queue, bid) -> None:
    awareness_queue.submit(bid)


def _default_ots_post(hash_hex: str, proof_path: "pathlib.Path") -> bool:
    """
    POST a SHA-256 hash to the OpenTimestamps public calendar server and
    save the returned .ots receipt to proof_path.

    OpenTimestamps is a free service anchored to the Bitcoin blockchain.
    No API key or account is required. The proof file received is a pending
    receipt — it is completed automatically within hours when the calendar
    operator includes it in a Bitcoin transaction.

    Returns True on success, False on any error.
    """
    import pathlib
    import urllib.request

    hash_bytes = bytes.fromhex(hash_hex)
    try:
        req = urllib.request.Request(
            OTS_CALENDAR_URL,
            data=hash_bytes,
            headers={"Content-Type": "application/octet-stream"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            proof_data = resp.read()
        pathlib.Path(proof_path).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(proof_path).write_bytes(proof_data)
        return True
    except Exception:
        return False
