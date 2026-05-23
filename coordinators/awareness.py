from __future__ import annotations

import uuid as _uuid
import time
from collections.abc import Callable
from typing import Any, TYPE_CHECKING

from coordinators.base import (
    Coordinator,
    append_turn_log_entry,
    backfill_coordinator_log_acceptance,
    build_turn_log_entry,
)
from coordinators.bid import Bid, BidQueue, PRIORITY_SAFETY
from coordinators.drive import Drive
from coordinators.memory import Memory
from coordinators.reason import Reason
from coordinators.sensory import Sensory
from coordinators.voice import Voice
from coordinators.orientation import Orientation
from coordinators.keeper import Keeper
from coordinators.mirror_user import MirrorUser
from coordinators.mirror_self import MirrorSelf
from coordinators.ethos import Ethos
from utils.time_utils import now_iso, unix_to_iso

if TYPE_CHECKING:
    from coordinators.hands import Hands


class Awareness:
    def __init__(
        self,
        sensory: Coordinator | None = None,
        memory: Memory | Coordinator | None = None,
        reason: Coordinator | None = None,
        voice: Voice | Coordinator | None = None,
        bid_queue: BidQueue | None = None,
        time_fn: Callable[[], float] = time.time,
        feeling: Coordinator | None = None,
        coordinator_log_acceptance_updater: Callable[[Any, bool], None] | None = None,
        hands: "Hands | None" = None,
        orientation: Orientation | Coordinator | None = None,
        keeper: Keeper | Coordinator | None = None,
        mirror_user: MirrorUser | Coordinator | None = None,
        mirror_self: MirrorSelf | Coordinator | None = None,
        ethos: Ethos | Coordinator | None = None,
        drive: Drive | Coordinator | None = None,
    ):
        self.sensory = sensory or Sensory()
        self.memory = memory or Memory()
        self.reason = reason or Reason(
            memory=self.memory if isinstance(self.memory, Memory) else None
        )
        self.voice = voice or Voice()
        self.hands = hands
        self.orientation = orientation or Orientation()
        self.keeper = keeper or Keeper()
        self.mirror_user = mirror_user or MirrorUser()
        self.mirror_self = mirror_self or MirrorSelf()
        self.ethos = ethos or Ethos()
        self.drive = drive or Drive()
        self._time_fn = time_fn
        self.session_id: str = _uuid.uuid4().hex
        self.session_start: float = self._time_fn()
        self.last_interaction_time: float = 0.0     # 0.0 = no prior interaction this session
        self.last_nrem_time: float = 0.0            # 0.0 = NREM has not run yet
                                                    # Dream Phase 2 (Task 47) updates this
        self.bid_queue = bid_queue or BidQueue()
        self.active_task_in_progress = False
        self.last_active = 0.0
        self._activity_callbacks: list[Callable[[float], None]] = []
        self.feeling = feeling  # may be None — Feeling is optional
        self.coordinator_log_acceptance_updater = (
            coordinator_log_acceptance_updater
            or _default_coordinator_log_acceptance_updater
        )

    def synchronous_run(self, message: str, **packet_overrides) -> dict:
        self._mark_active()
        self.active_task_in_progress = True
        packet = {"message": message, "input_type": "text"}
        packet.update(packet_overrides)
        packet["session_id"] = self.session_id
        import time as _turn_time
        packet["turn_id"] = _uuid.uuid4().hex
        packet["_turn_ts"] = _turn_time.time()

        # --- Temporal context -----------------------------------------------
        now = self._time_fn()
        time_since_input = (
            now - self.last_interaction_time
            if self.last_interaction_time > 0.0
            else None        # None = first interaction this session
        )
        time_since_nrem = (
            now - self.last_nrem_time
            if self.last_nrem_time > 0.0
            else None        # None = NREM has not run yet
        )
        time_since_autonomous = (
            now - self.last_active
            if self.last_active > 0.0
            else None
        )
        packet["current_time"] = unix_to_iso(now)
        packet["process_started_at"] = unix_to_iso(self.session_start)
        packet["session_age_seconds"] = now - self.session_start
        packet["time_since_last_interaction"] = time_since_input
        packet["time_since_last_nrem"] = time_since_nrem
        packet["time_since_last_autonomous_activity"] = time_since_autonomous
        self.last_interaction_time = now
        # ---------------------------------------------------------------------
        try:
            # --- Drive: budget state + shutdown_mode -------------------------
            # Must run before assess_tier so shutdown_mode is available before
            # tier selection. Failure is non-fatal for the foreground pipeline.
            try:
                packet = self.drive.process(packet)
            except Exception:
                pass
            # -----------------------------------------------------------------

            self.assess_tier(packet)

            packet = self.sensory.process(packet)
            if "error" in packet:
                packet = self.voice.process(packet)
                _write_turn_log(packet)
                return packet

            packet = self.memory.process(packet)
            if "error" in packet:
                packet = self.voice.process(packet)
                _write_turn_log(packet)
                return packet

            self._drain_bids_into_packet(packet)

            # --- Orientation: situation awareness digest ----------------------
            # Runs after bid drain (needs background_bids for salience scoring)
            # and before Reason (injects orientation_context into memory_context).
            try:
                packet = self.orientation.process(packet)
                orientation_ctx = str(packet.get("orientation_context") or "").strip()
                if orientation_ctx:
                    memory_context = str(packet.get("memory_context") or "").strip()
                    packet["memory_context"] = (
                        f"{memory_context}\n\n{orientation_ctx}"
                        if memory_context
                        else orientation_ctx
                    )
            except Exception:
                pass  # Orientation failure is non-fatal -- pipeline continues
            # -----------------------------------------------------------------

            # --- Keeper: trust level gate -------------------------------------
            # Runs after Orientation and before Reason so Reason receives the
            # current autonomy constraints in the packet and memory context.
            try:
                packet = self.keeper.process(packet)
            except Exception:
                pass  # Keeper failure is non-fatal -- pipeline continues
            # -----------------------------------------------------------------

            # --- Mirror-User: user affect model ------------------------------
            # Models user emotional state per-turn; must run after Keeper so
            # trust level is known, and before Mirror-Self so self-affect can
            # respond to user state.
            try:
                packet = self.mirror_user.process(packet)
            except Exception:
                pass  # Mirror-User failure is non-fatal -- pipeline continues
            # -----------------------------------------------------------------

            # --- Mirror-Self: generative model -------------------------------
            # Compares last turn's prediction against this message, then forms
            # the next prediction from Orientation before Reason runs.
            try:
                packet = self.mirror_self.process(packet)
            except Exception:
                pass  # Mirror-Self failure is non-fatal -- pipeline continues
            # -----------------------------------------------------------------

            # --- Ethos: behavioral doctrine injection -------------------------
            # Reads active immutable Doctrine nodes and injects doctrine_context
            # into memory_context before Reason selects behavior.
            try:
                packet = self.ethos.process(packet)
            except Exception:
                pass  # Ethos failure is non-fatal -- pipeline continues
            # -----------------------------------------------------------------

            packet = self.reason.process(packet)
            if self.hands is not None and "action" in packet:
                packet = self.hands.process(packet)
            packet = self.voice.process(packet)
            _write_turn_log(packet)
            if self.feeling is not None:
                observable = _extract_feeling_text(packet)
                if observable:
                    self.feeling.observe(observable)
            return packet
        finally:
            self.active_task_in_progress = False
            self._mark_active()

    def run(self, message: str, **packet_overrides) -> dict:
        return self.synchronous_run(message, **packet_overrides)

    async def gate_bids(self) -> list[Bid]:
        if self.active_task_in_progress or self.bid_queue.empty():
            return []
        bids = self.bid_queue.get_pending()
        self._mark_bids_accepted(bids)
        return bids

    def assess_tier(self, packet: dict) -> dict:
        from coordinators.tier_config import (
            DEFAULT_TIER,
            TIER_ENHANCED,
            TIER_LOCAL,
            apply_shutdown_cap,
            get_tier_name,
        )

        if "tier" in packet:
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
        packet["shutdown_mode"] = shutdown_mode
        return packet

    def add_activity_callback(self, callback: Callable[[float], None]) -> None:
        if callback not in self._activity_callbacks:
            self._activity_callbacks.append(callback)

    def _mark_active(self) -> None:
        self.last_active = self._time_fn()
        for callback in list(self._activity_callbacks):
            callback(self.last_active)

    def _drain_bids_into_packet(self, packet: dict) -> None:
        bids = self.bid_queue.get_pending()
        self._mark_bids_accepted(bids)
        packet["background_bids"] = [
            {k: getattr(bid, k, None) for k in
             ("coordinator_name", "content", "priority", "timestamp")}
            for bid in bids
        ]

        # --- Separate inner defender alerts from normal coordinator bids ---
        # PRIORITY_SAFETY bids are inner defender NE spikes — they must be
        # visible to Reason before any other bid context so the threat level
        # is unambiguous.
        defender_bids = [
            b for b in bids
            if getattr(b, "priority", PRIORITY_SAFETY + 1) <= PRIORITY_SAFETY
        ]
        normal_bids = [
            b for b in bids
            if getattr(b, "priority", PRIORITY_SAFETY + 1) > PRIORITY_SAFETY
        ]

        defender_context = _format_defender_context(defender_bids)
        bid_context = _format_bid_context(normal_bids)

        packet["defender_alerts"] = defender_context   # "" when none active
        packet["bid_context"] = bid_context

        # Build memory_context: defender alerts first, then normal bids.
        parts = []
        if defender_context:
            parts.append(defender_context)
        if bid_context:
            parts.append(bid_context)
        combined = "\n\n".join(parts)

        if not combined:
            return

        memory_context = str(packet.get("memory_context") or "").strip()
        if memory_context:
            packet["memory_context"] = f"{memory_context}\n\n{combined}"
        else:
            packet["memory_context"] = combined

    def _mark_bids_accepted(self, bids: list[Any]) -> None:
        for bid in bids:
            try:
                self.coordinator_log_acceptance_updater(bid, True)
            except Exception:
                continue


def _extract_feeling_text(packet: dict) -> str:
    parts = []
    for key in ("message", "reason_output", "error"):
        val = packet.get(key)
        if val:
            parts.append(str(val).strip())
    return " ".join(parts)


def _write_turn_log(packet: dict) -> None:
    try:
        turn_entry = build_turn_log_entry(packet)
        append_turn_log_entry(turn_entry)
    except Exception:
        pass


def _format_bid_context(bids: list[Bid]) -> str:
    if not bids:
        return ""

    lines = ["Background coordinator bids:"]
    for bid in bids:
        content = str(bid.content).strip()
        if not content:
            continue
        lines.append(
            f"- {bid.coordinator_name} (priority {bid.priority}): {content}"
        )
    return "\n".join(lines).strip()


def _format_defender_context(bids: list) -> str:
    if not bids:
        return ""
    lines = ["⚠ INNER DEFENDER ALERT ⚠"]
    for bid in bids:
        content = str(getattr(bid, "content", "")).strip()
        if content:
            lines.append(f"  {content}")
    return "\n".join(lines).strip()


def _default_coordinator_log_acceptance_updater(bid: Any, accepted: bool) -> None:
    coordinator_name = getattr(bid, "coordinator_name", "")
    timestamp = getattr(bid, "timestamp", 0.0)
    # TODO: improve bid-to-log matching with stable bid IDs instead of approximate timestamp matching.
    backfill_coordinator_log_acceptance(coordinator_name, timestamp, accepted)
