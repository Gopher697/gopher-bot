from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime
from types import SimpleNamespace


def _clock(year=2026, month=5, day=19):
    return lambda: datetime(year, month, day, tzinfo=UTC)


def _commitment(
    commitment_id: str,
    review_trigger: str | None,
    status: str = "active",
) -> dict:
    item = {"id": commitment_id, "status": status}
    if review_trigger is not None:
        item["review_trigger"] = review_trigger
    return item


# ── record_api_call() ────────────────────────────────────────────────────────

def test_tier_2_call_increments_session_api_calls_by_one():
    from coordinators.drive import Drive

    drive = Drive(commitments_reader=lambda: [], clock=_clock())

    drive.record_api_call(2)

    assert drive.state.session_api_calls[2] == 1


def test_tier_3_call_adds_tier_estimate_when_cost_is_none():
    from coordinators.drive import Drive, TIER_COST_ESTIMATES

    drive = Drive(commitments_reader=lambda: [], clock=_clock())

    drive.record_api_call(3)

    assert drive.state.session_budget_used == TIER_COST_ESTIMATES[3]


def test_explicit_cost_overrides_tier_estimate():
    from coordinators.drive import Drive

    drive = Drive(commitments_reader=lambda: [], clock=_clock())

    drive.record_api_call(3, cost=0.25)

    assert drive.state.session_budget_used == 0.25


def test_tier_1_call_adds_zero_to_session_budget_used():
    from coordinators.drive import Drive

    drive = Drive(commitments_reader=lambda: [], clock=_clock())

    drive.record_api_call(1)

    assert drive.state.session_budget_used == 0.0


def test_multiple_api_calls_accumulate_correctly():
    from coordinators.drive import Drive

    drive = Drive(commitments_reader=lambda: [], clock=_clock())

    drive.record_api_call(2)
    drive.record_api_call(3)
    drive.record_api_call(2, cost=0.04)

    assert drive.state.session_api_calls == {1: 0, 2: 2, 3: 1}
    assert drive.state.session_budget_used == 0.15


# ── Budget warning threshold ─────────────────────────────────────────────────

def test_no_pending_warning_below_eighty_percent_of_ceiling():
    from coordinators.drive import Drive

    drive = Drive(commitments_reader=lambda: [], clock=_clock(), budget_ceiling=1.0)

    drive.record_api_call(2, cost=0.79)

    assert drive.state.pending_budget_warning is None


def test_pending_warning_at_exactly_eighty_percent_of_ceiling():
    from coordinators.drive import Drive

    drive = Drive(commitments_reader=lambda: [], clock=_clock(), budget_ceiling=1.0)

    drive.record_api_call(2, cost=0.80)

    assert drive.state.pending_budget_warning is not None
    assert "80%" in drive.state.pending_budget_warning


def test_pending_warning_above_eighty_percent_of_ceiling():
    from coordinators.drive import Drive

    drive = Drive(commitments_reader=lambda: [], clock=_clock(), budget_ceiling=1.0)

    drive.record_api_call(3, cost=0.90)

    assert drive.state.pending_budget_warning is not None
    assert "$0.90" in drive.state.pending_budget_warning


# ── background_tick(): commitment staleness ──────────────────────────────────

def test_stalled_commitment_with_past_review_trigger_produces_bid():
    from coordinators.bid import BidQueue
    from coordinators.drive import Drive

    queue = BidQueue()
    drive = Drive(
        commitments_reader=lambda: [_commitment("C-001", "2026-05-18")],
        clock=_clock(2026, 5, 19),
    )

    asyncio.run(drive.background_tick(queue))

    assert queue.qsize() == 1


def test_active_commitment_with_future_review_trigger_produces_no_staleness_bid():
    from coordinators.bid import BidQueue
    from coordinators.drive import Drive

    queue = BidQueue()
    drive = Drive(
        commitments_reader=lambda: [_commitment("C-001", "2026-05-20")],
        clock=_clock(2026, 5, 19),
    )

    asyncio.run(drive.background_tick(queue))

    assert queue.qsize() == 0


def test_unparseable_review_trigger_is_not_stalled_and_does_not_error():
    from coordinators.bid import BidQueue
    from coordinators.drive import Drive

    queue = BidQueue()
    drive = Drive(
        commitments_reader=lambda: [_commitment("C-001", "First live session")],
        clock=_clock(),
    )

    asyncio.run(drive.background_tick(queue))

    assert queue.qsize() == 0


def test_missing_review_trigger_is_not_stalled_and_does_not_error():
    from coordinators.bid import BidQueue
    from coordinators.drive import Drive

    queue = BidQueue()
    drive = Drive(
        commitments_reader=lambda: [_commitment("C-001", None)],
        clock=_clock(),
    )

    asyncio.run(drive.background_tick(queue))

    assert queue.qsize() == 0


def test_stalled_commitment_ids_updated_after_tick():
    from coordinators.bid import BidQueue
    from coordinators.drive import Drive

    drive = Drive(
        commitments_reader=lambda: [
            _commitment("C-001", "2026-05-18"),
            _commitment("C-002", "2026-05-20"),
        ],
        clock=_clock(2026, 5, 19),
    )

    asyncio.run(drive.background_tick(BidQueue()))

    assert drive.state.stalled_commitment_ids == ["C-001"]


# ── background_tick(): no-nag rule ───────────────────────────────────────────

def test_same_observation_on_consecutive_ticks_does_not_produce_second_bid():
    from coordinators.bid import BidQueue
    from coordinators.drive import Drive

    queue = BidQueue()
    drive = Drive(
        commitments_reader=lambda: [_commitment("C-001", "2026-05-18")],
        clock=_clock(2026, 5, 19),
    )

    asyncio.run(drive.background_tick(queue))
    assert queue.qsize() == 1
    queue.clear()
    asyncio.run(drive.background_tick(queue))

    assert queue.qsize() == 0


def test_changed_observation_on_second_tick_produces_bid():
    from coordinators.bid import BidQueue
    from coordinators.drive import Drive

    commitment_sets = [
        [_commitment("C-001", "2026-05-18")],
        [
            _commitment("C-001", "2026-05-18"),
            _commitment("C-002", "2026-05-18"),
        ],
    ]
    queue = BidQueue()
    drive = Drive(
        commitments_reader=lambda: commitment_sets.pop(0),
        clock=_clock(2026, 5, 19),
    )

    asyncio.run(drive.background_tick(queue))
    queue.clear()
    asyncio.run(drive.background_tick(queue))

    assert queue.qsize() == 1
    assert "C-002" in queue.get_pending()[0].content


# ── background_tick(): nothing to surface ────────────────────────────────────

def test_no_stalled_commitments_and_no_budget_warning_submits_no_bid():
    from coordinators.bid import BidQueue
    from coordinators.drive import Drive

    queue = BidQueue()
    drive = Drive(commitments_reader=lambda: [], clock=_clock())

    asyncio.run(drive.background_tick(queue))

    assert queue.qsize() == 0


# ── background_tick(): bid fields ────────────────────────────────────────────

def test_bid_source_is_drive():
    from coordinators.bid import BidQueue
    from coordinators.drive import Drive

    queue = BidQueue()
    drive = Drive(
        commitments_reader=lambda: [_commitment("C-001", "2026-05-18")],
        clock=_clock(2026, 5, 19),
    )

    asyncio.run(drive.background_tick(queue))

    assert queue.get_pending()[0].source == "drive"


def test_bid_priority_is_drive_priority_six():
    from coordinators.bid import BidQueue
    from coordinators.drive import DRIVE_PRIORITY, Drive

    queue = BidQueue()
    drive = Drive(
        commitments_reader=lambda: [_commitment("C-001", "2026-05-18")],
        clock=_clock(2026, 5, 19),
    )

    asyncio.run(drive.background_tick(queue))

    assert queue.get_pending()[0].priority == DRIVE_PRIORITY == 6


def test_bid_type_is_progress_check():
    from coordinators.bid import BidQueue
    from coordinators.drive import Drive

    queue = BidQueue()
    drive = Drive(
        commitments_reader=lambda: [_commitment("C-001", "2026-05-18")],
        clock=_clock(2026, 5, 19),
    )

    asyncio.run(drive.background_tick(queue))

    assert queue.get_pending()[0].type == "progress_check"


def test_bid_content_contains_commitment_id_when_stalled():
    from coordinators.bid import BidQueue
    from coordinators.drive import Drive

    queue = BidQueue()
    drive = Drive(
        commitments_reader=lambda: [_commitment("C-004", "2026-05-18")],
        clock=_clock(2026, 5, 19),
    )

    asyncio.run(drive.background_tick(queue))

    assert "C-004" in queue.get_pending()[0].content


# ── background_tick(): state ─────────────────────────────────────────────────

def test_last_tick_is_set_after_tick():
    from coordinators.bid import BidQueue
    from coordinators.drive import Drive

    drive = Drive(commitments_reader=lambda: [], clock=_clock())

    asyncio.run(drive.background_tick(BidQueue()))

    assert drive.state.last_tick == _clock()()


def test_last_tick_is_none_before_first_tick():
    from coordinators.drive import Drive

    drive = Drive(commitments_reader=lambda: [], clock=_clock())

    assert drive.state.last_tick is None


# ── process() ────────────────────────────────────────────────────────────────

def test_process_attaches_drive_budget_status_to_returned_packet():
    from coordinators.drive import Drive

    packet = Drive(commitments_reader=lambda: [], clock=_clock()).process({})

    assert "drive_budget_status" in packet


def test_process_calls_record_api_call_when_model_tier_key_is_present():
    from coordinators.drive import Drive

    drive = Drive(commitments_reader=lambda: [], clock=_clock())
    packet = drive.process({"model_tier": 2})

    assert drive.state.session_api_calls[2] == 1
    assert packet["drive_budget_status"]["session_budget_used"] == 0.01


def test_process_does_not_call_record_api_call_when_model_tier_key_is_absent():
    from coordinators.drive import Drive

    drive = Drive(commitments_reader=lambda: [], clock=_clock())
    drive.process({})

    assert drive.state.session_api_calls == {1: 0, 2: 0, 3: 0}
    assert drive.state.session_budget_used == 0.0


def test_drive_budget_status_contains_expected_keys():
    from coordinators.drive import Drive

    packet = Drive(commitments_reader=lambda: [], clock=_clock()).process({})

    assert set(packet["drive_budget_status"]) == {
        "session_budget_used",
        "budget_ceiling",
        "budget_fraction",
        "api_calls_by_tier",
    }


def test_budget_fraction_is_zero_when_no_api_calls_have_been_made():
    from coordinators.drive import Drive

    packet = Drive(commitments_reader=lambda: [], clock=_clock()).process({})

    assert packet["drive_budget_status"]["budget_fraction"] == 0.0


# ── BrainLoop integration ────────────────────────────────────────────────────

def test_drive_is_registered_in_default_coordinator_registry():
    from coordinators.brain_loop import BrainLoop
    from coordinators.drive import Drive

    brain_loop = BrainLoop()

    assert isinstance(brain_loop.coordinators["drive"], Drive)
    assert brain_loop.intervals["drive"] == 86400.0


def test_drive_background_tick_has_standard_signature_without_mirror_queue():
    from coordinators.drive import Drive

    drive = Drive(commitments_reader=lambda: [], clock=_clock())

    assert len(inspect.signature(drive.background_tick).parameters) == 1


def test_brain_loop_calls_drive_with_standard_signature_after_refactor():
    from coordinators.bid import BidQueue
    from coordinators.brain_loop import BrainLoop
    from coordinators.drive import Drive

    current_time = [1000.0]
    queue = BidQueue()
    drive = Drive(
        commitments_reader=lambda: [_commitment("C-001", "2026-05-18")],
        clock=_clock(2026, 5, 19),
    )
    awareness = SimpleNamespace(
        bid_queue=queue,
        last_active=current_time[0],
        mirror_chad_queue=object(),
    )
    brain_loop = BrainLoop(
        coordinators={"drive": drive},
        intervals={"drive": 86400.0},
        time_fn=lambda: current_time[0],
        sleep_interval=0,
    )
    brain_loop.bind_awareness(awareness)

    asyncio.run(brain_loop.tick_once())

    assert brain_loop.last_errors == {}
    assert queue.qsize() == 1
