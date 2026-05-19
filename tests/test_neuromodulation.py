from __future__ import annotations

import asyncio

import pytest


class RecordingBidQueue:
    def __init__(self):
        self.submitted = []
        self.put_items = []

    def submit(self, item):
        self.submitted.append(item)

    def put_nowait(self, item):
        self.put_items.append(item)


def _neuromodulation(**kwargs):
    from coordinators.neuromodulation import Neuromodulation

    kwargs.setdefault("state_reader", lambda: None)
    kwargs.setdefault("state_writer", lambda _: None)
    return Neuromodulation(**kwargs)


def test_default_effective_levels_match_tonic_baselines():
    from coordinators.neuromodulation import DEFAULT_TONIC_LEVELS

    neuromodulation = _neuromodulation()

    assert neuromodulation.get_output_params() == {
        "learning_rate": DEFAULT_TONIC_LEVELS["DA"],
        "exploration_bias": DEFAULT_TONIC_LEVELS["NE"],
        "consolidation_patience": DEFAULT_TONIC_LEVELS["5HT"],
        "attention": DEFAULT_TONIC_LEVELS["ACh"],
    }


def test_phasic_starts_at_zero_for_all_channels():
    neuromodulation = _neuromodulation()

    assert all(
        channel.phasic == 0.0
        for channel in neuromodulation.state.channels.values()
    )


def test_inject_da_raises_da_phasic_and_suppresses_5ht_phasic():
    neuromodulation = _neuromodulation(
        state_reader=lambda: {
            "DA_tonic": 0.5,
            "DA_phasic": 0.0,
            "5HT_tonic": 0.6,
            "5HT_phasic": 0.5,
        }
    )

    neuromodulation.inject_phasic("DA", 0.3)

    assert neuromodulation.state.channels["DA"].phasic == pytest.approx(0.3)
    assert neuromodulation.state.channels["5HT"].phasic == pytest.approx(0.38)


def test_inject_5ht_raises_5ht_phasic_and_suppresses_da_phasic():
    neuromodulation = _neuromodulation(
        state_reader=lambda: {
            "DA_tonic": 0.5,
            "DA_phasic": 0.5,
            "5HT_tonic": 0.6,
            "5HT_phasic": 0.0,
        }
    )

    neuromodulation.inject_phasic("5HT", 0.3)

    assert neuromodulation.state.channels["5HT"].phasic == pytest.approx(0.3)
    assert neuromodulation.state.channels["DA"].phasic == pytest.approx(0.38)


def test_inject_phasic_clamps_to_channel_ceiling():
    neuromodulation = _neuromodulation()

    neuromodulation.inject_phasic("NE", 2.0)

    assert neuromodulation.state.channels["NE"].phasic == 1.0


def test_inject_phasic_clamps_negative_to_zero():
    neuromodulation = _neuromodulation(
        state_reader=lambda: {"NE_tonic": 0.4, "NE_phasic": 0.2}
    )

    neuromodulation.inject_phasic("NE", -1.0)

    assert neuromodulation.state.channels["NE"].phasic == 0.0


def test_inject_unknown_channel_raises_value_error():
    neuromodulation = _neuromodulation()

    with pytest.raises(ValueError):
        neuromodulation.inject_phasic("unknown", 0.1)


def test_phasic_decays_toward_zero_after_tick():
    neuromodulation = _neuromodulation()
    neuromodulation.inject_phasic("ACh", 0.5)

    asyncio.run(neuromodulation.background_tick(RecordingBidQueue()))

    decayed = neuromodulation.state.channels["ACh"].phasic
    assert 0.0 < decayed < 0.5


def test_phasic_decay_uses_five_minute_half_life_for_thirty_second_tick():
    neuromodulation = _neuromodulation()
    neuromodulation.inject_phasic("ACh", 0.5)

    asyncio.run(neuromodulation.background_tick(RecordingBidQueue()))

    assert neuromodulation.state.channels["ACh"].phasic == pytest.approx(
        0.5 * (0.5 ** (30.0 / 300.0))
    )


def test_phasic_floors_to_zero_below_threshold():
    neuromodulation = _neuromodulation(
        state_reader=lambda: {"DA_tonic": 0.5, "DA_phasic": 0.004}
    )

    asyncio.run(neuromodulation.background_tick(RecordingBidQueue()))

    assert neuromodulation.state.channels["DA"].phasic == 0.0


def test_get_output_params_returns_all_expected_keys():
    params = _neuromodulation().get_output_params()

    assert set(params) == {
        "learning_rate",
        "exploration_bias",
        "consolidation_patience",
        "attention",
    }


def test_get_output_params_values_are_in_unit_interval():
    neuromodulation = _neuromodulation()
    neuromodulation.inject_phasic("DA", 0.8)
    neuromodulation.inject_phasic("NE", 0.8)
    neuromodulation.inject_phasic("5HT", 0.8)
    neuromodulation.inject_phasic("ACh", 0.8)

    assert all(0.0 <= value <= 1.0 for value in neuromodulation.get_output_params().values())


def test_state_saves_and_loads_from_json_round_trip(tmp_path, monkeypatch):
    import coordinators.neuromodulation as module
    from coordinators.neuromodulation import Neuromodulation

    state_path = tmp_path / "neuromodulation_state.json"
    monkeypatch.setattr(module, "_NEUROMODULATION_STATE_PATH", state_path)

    first = Neuromodulation(state_reader=lambda: None)
    first.inject_phasic("DA", 0.25)

    asyncio.run(first.background_tick(RecordingBidQueue()))
    second = Neuromodulation()

    assert state_path.exists()
    assert second.state.channels["DA"].tonic == first.state.channels["DA"].tonic
    assert second.state.channels["DA"].phasic == pytest.approx(
        first.state.channels["DA"].phasic
    )


def test_state_snapshot_serializes_all_eight_fields():
    neuromodulation = _neuromodulation()

    assert set(neuromodulation.snapshot()) == {
        "DA_tonic",
        "DA_phasic",
        "NE_tonic",
        "NE_phasic",
        "5HT_tonic",
        "5HT_phasic",
        "ACh_tonic",
        "ACh_phasic",
    }


def test_background_tick_saves_state_after_decay():
    snapshots = []
    neuromodulation = _neuromodulation(state_writer=snapshots.append)
    neuromodulation.inject_phasic("NE", 0.2)

    asyncio.run(neuromodulation.background_tick(RecordingBidQueue()))

    assert len(snapshots) == 1
    assert snapshots[0]["NE_phasic"] == pytest.approx(
        neuromodulation.state.channels["NE"].phasic
    )


def test_background_tick_never_submits_to_bid_queue_submit():
    queue = RecordingBidQueue()
    neuromodulation = _neuromodulation()

    asyncio.run(neuromodulation.background_tick(queue))

    assert queue.submitted == []


def test_background_tick_never_puts_to_bid_queue_put_nowait():
    queue = RecordingBidQueue()
    neuromodulation = _neuromodulation()

    asyncio.run(neuromodulation.background_tick(queue))

    assert queue.put_items == []


def test_brain_loop_registers_neuromodulation_at_thirty_second_cadence():
    from coordinators.brain_loop import BrainLoop
    from coordinators.neuromodulation import Neuromodulation

    brain_loop = BrainLoop()

    assert isinstance(brain_loop.coordinators["neuromodulation"], Neuromodulation)
    assert brain_loop.intervals["neuromodulation"] == 30.0


def test_neuromodulation_background_tick_has_standard_signature():
    from coordinators.brain_loop import _accepts_mirror_queue

    assert _accepts_mirror_queue(_neuromodulation()) is False
