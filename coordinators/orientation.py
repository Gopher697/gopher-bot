from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from coordinators.base import Coordinator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_models import config, graph  # noqa: E402


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROMOTION_CONFIDENCE_THRESHOLD: float = 0.6
PROMOTION_SALIENCE_THRESHOLD: float = 0.5
ORIENTATION_MAX_GOALS: int = 3
ORIENTATION_MAX_DEFERRED: int = 3
ORIENTATION_HIGH_PRIORITY_THRESHOLD: float = 0.7

# Salience recency window: last_advanced_at this many seconds ago → zero recency contribution
SALIENCE_RECENCY_DECAY_SECONDS: float = 86400.0 * 3   # 3 days

# Horizon weights: how immediately salient is a goal of this horizon?
SALIENCE_HORIZON_WEIGHTS: dict[str, float] = {
    "thread":       1.0,   # current conversational focus — highest urgency
    "project":      0.8,   # spans multiple threads
    "standing":     0.6,   # persistent indefinitely
    "exploratory":  0.4,   # open-ended, low immediate pressure
}


# ---------------------------------------------------------------------------
# Salience scoring — pure Python, no I/O, no graph writes
# ---------------------------------------------------------------------------

def _compute_salience(
    goal: dict,
    now_ts: float,
    bid_keywords: set[str],
) -> float:
    """
    Compute a momentary salience score in [0.0, 1.0].

    Salience is never stored — it is computed fresh each orientation pass.

    Factors and weights:
    - priority (0.40): stored intent weight set at creation/update
    - horizon_weight (0.35): thread > project > standing > exploratory
    - recency (0.25): time since last_advanced_at; peaks when recently advanced,
      decays to 0 at SALIENCE_RECENCY_DECAY_SECONDS
    - bid_boost (up to +0.20, applied after weighting): content overlap with
      active coordinator bid keywords signals external pressure toward this goal
    - staleness multiplier (0.60 if stale, 1.0 if fresh): penalty for stale
      candidates or goals not recently checked

    Args:
        goal:         Goal property dict from the graph.
        now_ts:       Current time as Unix timestamp.
        bid_keywords: Lowercased word set extracted from background bid content.

    Returns:
        Salience score in [0.0, 1.0].
    """
    from datetime import datetime, timezone

    priority = float(goal.get("priority", 0.5))
    horizon = goal.get("horizon", "exploratory")
    horizon_weight = SALIENCE_HORIZON_WEIGHTS.get(horizon, 0.4)

    # Recency contribution: how recently was this goal last advanced?
    recency_score = 0.0
    last_advanced_str = goal.get("last_advanced_at")
    if last_advanced_str:
        try:
            la = datetime.fromisoformat(last_advanced_str)
            if la.tzinfo is None:
                la = la.replace(tzinfo=timezone.utc)
            age_seconds = (
                datetime.fromtimestamp(now_ts, tz=timezone.utc) - la
            ).total_seconds()
            recency_score = max(
                0.0,
                1.0 - age_seconds / SALIENCE_RECENCY_DECAY_SECONDS,
            )
        except (ValueError, TypeError, OSError):
            recency_score = 0.0

    # Staleness multiplier: stale goals exert less pressure
    staleness_state = goal.get("staleness_state", "fresh")
    staleness_multiplier = 0.6 if staleness_state == "stale" else 1.0

    # Bid pressure boost: does any active coordinator bid mention this goal?
    bid_boost = 0.0
    if bid_keywords:
        content_words = set(goal.get("content", "").lower().split())
        overlap = content_words & bid_keywords
        if overlap:
            bid_boost = min(0.20, len(overlap) * 0.05)

    raw = (
        priority * 0.40
        + horizon_weight * 0.35
        + recency_score * 0.25
        + bid_boost
    ) * staleness_multiplier

    return min(1.0, max(0.0, raw))


# ---------------------------------------------------------------------------
# Promotion gate — three-score check: confidence + salience + permissibility
# ---------------------------------------------------------------------------

def _passes_promotion_gate(
    goal: dict,
    salience: float,
) -> tuple[bool, str]:
    """
    Evaluate whether a candidate goal should be promoted to 'active'.

    Three scores checked in order:
    1. Confidence >= PROMOTION_CONFIDENCE_THRESHOLD (epistemics: is this real?)
    2. Salience >= PROMOTION_SALIENCE_THRESHOLD (relevance: does this matter now?)
    3. Permissibility: charter_alignment != 'false' (governance: may we pursue it?)

    Args:
        goal:     Goal property dict.
        salience: Precomputed salience score for this goal.

    Returns:
        Tuple (passes: bool, reason: str). The reason string is auditable.
    """
    confidence = float(goal.get("confidence", 0.0))
    charter_alignment = str(goal.get("charter_alignment", "uncertain"))

    if confidence < PROMOTION_CONFIDENCE_THRESHOLD:
        return (
            False,
            f"confidence {confidence:.2f} < threshold {PROMOTION_CONFIDENCE_THRESHOLD:.2f}",
        )

    if salience < PROMOTION_SALIENCE_THRESHOLD:
        return (
            False,
            f"salience {salience:.2f} < threshold {PROMOTION_SALIENCE_THRESHOLD:.2f}",
        )

    if charter_alignment == "false":
        return (
            False,
            "permissibility gate failed: charter_alignment='false'",
        )

    return (
        True,
        f"passes all gates (confidence={confidence:.2f}, "
        f"salience={salience:.2f}, charter={charter_alignment})",
    )


# ---------------------------------------------------------------------------
# Packet field extraction helpers — no I/O
# ---------------------------------------------------------------------------

def _extract_bid_keywords(packet: dict) -> set[str]:
    """
    Extract a lowercased word set from background bid content in the packet.

    Used for bid-pressure boost in salience scoring. Pulls from
    packet["background_bids"] (list of bid dicts) and packet["bid_context"]
    (pre-formatted string). Stopwords filtered out.
    """
    _STOPWORDS = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "to", "of", "in",
        "on", "at", "for", "with", "by", "from", "and", "or", "but",
        "not", "it", "its", "this", "that", "i", "you", "we", "they",
    }
    words: set[str] = set()

    bids = packet.get("background_bids") or []
    for bid in bids:
        content = str(bid.get("content", "")).lower()
        words.update(w for w in content.split() if w not in _STOPWORDS and len(w) > 2)

    bid_context = str(packet.get("bid_context", "") or "").lower()
    words.update(w for w in bid_context.split() if w not in _STOPWORDS and len(w) > 2)

    return words


def _thread_context(packet: dict) -> str:
    """Summarise the current thread state from packet temporal fields."""
    time_since = packet.get("time_since_last_interaction")
    message = str(packet.get("message", "")).strip()
    preview = (message[:80] + "…") if len(message) > 80 else message

    if time_since is None:
        prefix = "First interaction this process run."
    else:
        minutes = int(time_since / 60)
        if minutes < 2:
            prefix = "Thread is active (last input < 2 min ago)."
        elif minutes < 60:
            prefix = f"Thread resumed after {minutes}m gap."
        else:
            hours = round(time_since / 3600, 1)
            prefix = f"Thread resumed after {hours}h gap."

    if preview:
        return f"{prefix} Current input: \"{preview}\""
    return prefix


def _operational_context(packet: dict, now_ts: float) -> str:
    """
    Build a one-liner operational summary from packet temporal fields.

    Reports process uptime, time since last NREM, and time since last
    autonomous activity.
    """
    parts: list[str] = []

    session_age = packet.get("session_age_seconds")
    if session_age is not None:
        h = int(session_age) // 3600
        m = (int(session_age) % 3600) // 60
        parts.append(f"Process up {h}h{m}m")

    nrem = packet.get("time_since_last_nrem")
    if nrem is None:
        parts.append("NREM: never run")
    else:
        nrem_h = round(nrem / 3600, 1)
        parts.append(f"NREM: {nrem_h}h ago")

    autonomous = packet.get("time_since_last_autonomous_activity")
    if autonomous is not None:
        auto_m = int(autonomous / 60)
        parts.append(f"last autonomous: {auto_m}m ago")

    return " | ".join(parts) if parts else "Operational context unavailable."


def _extract_background_pressures(packet: dict) -> list[str]:
    """
    Extract background coordinator signals as a flat list of strings.

    Returns the content of background bids, prefixed with coordinator name.
    Defender alerts are excluded (they appear separately as defender_alerts).
    """
    pressures: list[str] = []
    bids = packet.get("background_bids") or []
    for bid in bids:
        coordinator = str(bid.get("coordinator_name", "unknown"))
        content = str(bid.get("content", "")).strip()
        if content:
            pressures.append(f"[{coordinator}] {content}")
    return pressures


def _recent_shift(packet: dict) -> str:
    """Describe what changed recently based on packet temporal signals."""
    time_since = packet.get("time_since_last_interaction")
    defender_alerts = str(packet.get("defender_alerts", "") or "").strip()

    if defender_alerts:
        return "Inner Defender alert active — situation may have shifted."

    if time_since is None:
        return "No prior interaction this run — all context is new."

    if time_since < 30:
        return "Continuous thread — no significant shift detected."

    minutes = int(time_since / 60)
    return f"Thread resumed after {minutes}m — context may have shifted."


def _recommend_next_pressure(
    scored_active: list[dict],
    promotable: list[dict],
    packet: dict,
) -> str:
    """
    Synthesise a single recommended action or focus for the next turn.

    Priority hierarchy:
    1. Inner Defender alert (highest urgency — addressed before goals)
    2. Promotable candidate goal (AI has evaluated it as ready)
    3. Highest-salience active goal (continuity pressure)
    4. Background bid pressure from Drive or Curiosity
    5. No urgent pressure
    """
    defender_alerts = str(packet.get("defender_alerts", "") or "").strip()
    if defender_alerts:
        return "INNER DEFENDER alert is active — address it before advancing goals."

    if promotable:
        top = promotable[0]["goal"]
        content_preview = (top["content"][:60] + "…") if len(top["content"]) > 60 else top["content"]
        return f"Goal ready for promotion: \"{content_preview}\""

    if scored_active:
        top = scored_active[0]
        sal = top["salience"]
        content = top["goal"]["content"]
        preview = (content[:60] + "…") if len(content) > 60 else content
        return f"Continue pursuing (salience={sal:.2f}): \"{preview}\""

    bids = packet.get("background_bids") or []
    for bid in bids:
        cname = str(bid.get("coordinator_name", ""))
        if cname in ("drive", "curiosity"):
            content = str(bid.get("content", "")).strip()
            if content:
                preview = (content[:60] + "…") if len(content) > 60 else content
                return f"{cname.capitalize()} signal: \"{preview}\""

    return "No urgent pressure identified — open to new direction."


# ---------------------------------------------------------------------------
# Goal summary helpers — for digest list items
# ---------------------------------------------------------------------------

def _goal_summary(scored_entry: dict) -> dict:
    """
    Build a concise summary dict for a scored active goal.

    Args:
        scored_entry: Dict with keys 'goal' (property dict) and 'salience' (float).

    Returns:
        Dict with goal_id, content, horizon, priority, salience, staleness_state,
        current_next_action (may be None).
    """
    goal = scored_entry["goal"]
    return {
        "goal_id":            goal.get("goal_id"),
        "content":            goal.get("content"),
        "horizon":            goal.get("horizon"),
        "priority":           goal.get("priority"),
        "salience":           round(scored_entry["salience"], 3),
        "staleness_state":    goal.get("staleness_state"),
        "current_next_action": goal.get("current_next_action"),
    }


def _goal_summary_brief(goal: dict) -> dict:
    """
    Build a minimal summary for deferred/do_not_forget goals.

    Args:
        goal: Goal property dict.

    Returns:
        Dict with goal_id, content, horizon, priority, review_after.
    """
    return {
        "goal_id":     goal.get("goal_id"),
        "content":     goal.get("content"),
        "horizon":     goal.get("horizon"),
        "priority":    goal.get("priority"),
        "review_after": goal.get("review_after"),
    }


# ---------------------------------------------------------------------------
# Digest assembly
# ---------------------------------------------------------------------------

def _build_digest(
    packet: dict,
    scored_active: list[dict],
    promotable: list[dict],
    deferred: list[dict],
    now_ts: float,
) -> dict:
    """
    Assemble the full orientation digest from pre-computed components.

    Args:
        packet:        The current packet (for temporal and bid fields).
        scored_active: List of {'goal': dict, 'salience': float}, sorted descending.
        promotable:    List of {'goal': dict, 'salience': float, 'reason': str}.
        deferred:      List of deferred goal property dicts.
        now_ts:        Current Unix timestamp.

    Returns:
        The orientation dict injected into packet["orientation"].
    """
    high_priority_deferred = [
        g for g in deferred
        if float(g.get("priority", 0.0)) >= ORIENTATION_HIGH_PRIORITY_THRESHOLD
    ]

    return {
        "thread_context":            _thread_context(packet),
        "operational_context":       _operational_context(packet, now_ts),
        "active_goal_focus":         (
            scored_active[0]["goal"]["content"]
            if scored_active else None
        ),
        "relevant_goals":            [
            _goal_summary(e)
            for e in scored_active[:ORIENTATION_MAX_GOALS]
        ],
        "unresolved_items":          [
            _goal_summary_brief(g)
            for g in deferred[:ORIENTATION_MAX_DEFERRED]
        ],
        "background_pressures":      _extract_background_pressures(packet),
        "recent_shift":              _recent_shift(packet),
        "do_not_forget":             [
            _goal_summary_brief(g)
            for g in high_priority_deferred[:ORIENTATION_MAX_DEFERRED]
        ],
        "recommended_next_pressure": _recommend_next_pressure(
            scored_active, promotable, packet
        ),
    }


def _format_orientation_context(orientation: dict) -> str:
    """
    Format the orientation digest as a plain-text string for Reason's context window.

    Reason receives this via packet["orientation_context"]. It is compact enough
    to stay within the context budget, surfacing only what matters this turn.
    """
    lines: list[str] = ["=== ORIENTATION ==="]

    thread = orientation.get("thread_context")
    if thread:
        lines.append(f"Thread: {thread}")

    operational = orientation.get("operational_context")
    if operational:
        lines.append(f"Operational: {operational}")

    focus = orientation.get("active_goal_focus")
    if focus:
        preview = (focus[:80] + "…") if len(focus) > 80 else focus
        lines.append(f"Active goal focus: {preview}")

    relevant = orientation.get("relevant_goals") or []
    if relevant:
        lines.append("Relevant goals:")
        for g in relevant:
            sal = g.get("salience", 0.0)
            content = str(g.get("content", ""))
            preview = (content[:70] + "…") if len(content) > 70 else content
            lines.append(f"  [{sal:.2f}] {preview}")

    do_not_forget = orientation.get("do_not_forget") or []
    if do_not_forget:
        lines.append("Do not forget (deferred, high priority):")
        for g in do_not_forget:
            content = str(g.get("content", ""))
            preview = (content[:70] + "…") if len(content) > 70 else content
            lines.append(f"  • {preview}")

    pressures = orientation.get("background_pressures") or []
    if pressures:
        lines.append("Background pressures:")
        for p in pressures[:3]:  # cap at 3 in the text view
            lines.append(f"  {p}")

    recommended = orientation.get("recommended_next_pressure")
    if recommended:
        lines.append(f"Recommended: {recommended}")

    recent_shift = orientation.get("recent_shift")
    if recent_shift:
        lines.append(f"Shift: {recent_shift}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orientation coordinator class
# ---------------------------------------------------------------------------

class Orientation(Coordinator):
    """
    Orientation coordinator — Endsley Level 3 projection.

    Runs in the foreground pipeline before Reason. Queries active, candidate,
    and deferred goals from the graph; computes salience; auto-promotes
    candidates that pass the three-score gate; builds the orientation digest;
    injects it into the packet.

    Does not make LLM calls. All intelligence is structural.
    """

    name = "orientation"

    def __init__(
        self,
        environment: str = "global",
        promotion_rule_version: str = "v1",
    ) -> None:
        self.environment = environment
        self.promotion_rule_version = promotion_rule_version

    def process(self, packet: dict) -> dict:
        """
        Build and inject the orientation digest into the packet.

        On exception (graph unavailable, etc.), logs a soft failure and injects
        an empty orientation rather than propagating the error.

        Packet fields written:
        - packet["orientation"]         — structured digest dict
        - packet["orientation_context"] — plain-text version for Reason
        - packet["promotable_goal_ids"] — list of goal_ids promoted this turn
        """
        now_ts = time.time()
        environment = packet.get("environment", self.environment)

        active: list[dict] = []
        candidates: list[dict] = []
        deferred: list[dict] = []
        driver = None

        try:
            driver = graph.connect()
            active = graph.get_active_goals(driver, environment)
            candidates = graph.get_candidate_goals(driver, environment)
            deferred = graph.get_deferred_goals(driver, environment)
        except Exception:
            # Graph unavailable — orientation runs with empty goal lists
            pass
        finally:
            if driver is not None:
                try:
                    graph.close(driver)
                except Exception:
                    pass

        # Extract bid keyword pressure for salience scoring
        bid_keywords = _extract_bid_keywords(packet)

        # Score active (and dormant) goals by salience
        scored_active = sorted(
            [
                {"goal": g, "salience": _compute_salience(g, now_ts, bid_keywords)}
                for g in active
            ],
            key=lambda x: x["salience"],
            reverse=True,
        )

        # Evaluate promotion gate for all candidates
        promotable: list[dict] = []
        for g in candidates:
            sal = _compute_salience(g, now_ts, bid_keywords)
            passes, reason = _passes_promotion_gate(g, sal)
            if passes:
                promotable.append({"goal": g, "salience": sal, "reason": reason})

        # Auto-promote candidates that passed the gate
        promoted_ids = self._promote_goals(promotable, environment)

        # Build the orientation digest
        orientation = _build_digest(
            packet=packet,
            scored_active=scored_active,
            promotable=promotable,
            deferred=deferred,
            now_ts=now_ts,
        )

        packet["orientation"] = orientation
        packet["orientation_context"] = _format_orientation_context(orientation)
        packet["promotable_goal_ids"] = promoted_ids

        return packet

    def _promote_goals(
        self,
        promotable: list[dict],
        environment: str,
    ) -> list[str]:
        """
        Write promotion transitions to the graph for all promotable candidates.

        Wraps each transition in try/except — a failed promotion does not
        abort the orientation pass.

        Returns:
            List of goal_ids that were successfully promoted this turn.
        """
        promoted: list[str] = []
        if not promotable:
            return promoted

        driver = None
        try:
            driver = graph.connect()
            for entry in promotable:
                goal = entry["goal"]
                goal_id = goal.get("goal_id")
                reason = entry["reason"]
                if not goal_id:
                    continue
                try:
                    graph.transition_goal_status(
                        driver=driver,
                        goal_id=goal_id,
                        environment=environment,
                        new_status="active",
                        promoted_by=self.name,
                        promotion_summary="Passed three-score gate during orientation pass.",
                        promotion_evidence=reason,
                        promotion_rule_version=self.promotion_rule_version,
                    )
                    promoted.append(goal_id)
                except (ValueError, Exception):
                    # Already promoted by a concurrent call, or transition illegal — skip
                    continue
        except Exception:
            pass
        finally:
            if driver is not None:
                try:
                    graph.close(driver)
                except Exception:
                    pass

        return promoted
