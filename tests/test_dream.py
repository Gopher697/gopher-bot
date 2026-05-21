from __future__ import annotations

import asyncio
from datetime import UTC, datetime


def _clock(year=2026, month=5, day=19, hour=12):
    return lambda: datetime(year, month, day, hour, tzinfo=UTC)


def _dream(**kwargs):
    from coordinators.dream import Dream

    kwargs.setdefault("clock", _clock())
    return Dream(**kwargs)


class RecordingAwarenessQueue:
    def __init__(self):
        self.submitted = []
        self.put_items = []

    def submit(self, item):
        self.submitted.append(item)

    def put_nowait(self, item):
        self.put_items.append(item)


# intake()

def test_intake_returns_dream_item():
    from coordinators.dream import DreamItem

    item = _dream().intake("maybe a small thought")

    assert isinstance(item, DreamItem)


def test_dream_item_text_matches_input_exactly():
    text = "  Maybe this spacing matters.  "

    item = _dream().intake(text)

    assert item.text == text


def test_dream_item_timestamp_is_set():
    item = _dream(clock=_clock()).intake("maybe")

    assert item.timestamp == _clock()()


def test_intake_appends_item_to_state_log():
    dream = _dream()

    item = dream.intake("maybe")

    assert list(dream.state.log) == [item]


def test_last_intake_is_updated_after_intake():
    dream = _dream(clock=_clock())

    dream.intake("maybe")

    assert dream.state.last_intake == _clock()()


def test_multiple_intakes_accumulate_in_log():
    dream = _dream()

    dream.intake("first")
    dream.intake("second")

    assert [item.text for item in dream.state.log] == ["first", "second"]


def test_log_respects_dream_log_maxlen_oldest_dropped_at_101st_intake():
    from coordinators.dream import DREAM_LOG_MAXLEN

    dream = _dream()

    for index in range(DREAM_LOG_MAXLEN + 1):
        dream.intake(f"item {index}")

    assert len(dream.state.log) == DREAM_LOG_MAXLEN
    assert dream.state.log[0].text == "item 1"


def test_dream_item_associations_empty_on_intake():
    item = _dream().intake("maybe")

    assert item.associations == []


# Tag detection - single tags

def test_what_if_text_tags_idea():
    item = _dream().intake("what if this connects")

    assert "idea" in item.tags


def test_question_mark_text_tags_question():
    item = _dream().intake("is this connected?")

    assert "question" in item.tags


def test_noticed_text_tags_observation():
    item = _dream().intake("noticed the pattern repeated")

    assert "observation" in item.tags


def test_frustrated_text_tags_feeling():
    item = _dream().intake("frustrated with the loop")

    assert "feeling" in item.tags


def test_text_with_no_marker_gets_fragment_only():
    item = _dream().intake("blue static under glass")

    assert item.tags == ["fragment"]


# Tag detection - multiple tags

def test_idea_and_question_mark_text_gets_both_tags_without_fragment():
    item = _dream().intake("what if this could work?")

    assert "idea" in item.tags
    assert "question" in item.tags
    assert "fragment" not in item.tags


def test_fragment_absent_when_any_other_tag_matched():
    item = _dream().intake("noticed something")

    assert "fragment" not in item.tags


# Tag detection - ordering

def test_idea_appears_before_feeling_when_both_match():
    item = _dream().intake("maybe I am excited about this")

    assert item.tags.index("idea") < item.tags.index("feeling")


# background_tick() - association pass

def test_two_items_sharing_tag_get_each_others_indices_after_tick():
    dream = _dream()
    dream.intake("maybe first")
    dream.intake("what if second")

    asyncio.run(dream.background_tick(RecordingAwarenessQueue()))

    assert dream.state.log[0].associations == [1]
    assert dream.state.log[1].associations == [0]


def test_two_items_with_no_shared_tags_do_not_get_associations():
    dream = _dream()
    dream.intake("maybe first")
    dream.intake("noticed second")

    asyncio.run(dream.background_tick(RecordingAwarenessQueue()))

    assert dream.state.log[0].associations == []
    assert dream.state.log[1].associations == []


def test_associations_do_not_duplicate_on_repeated_ticks():
    dream = _dream()
    dream.intake("maybe first")
    dream.intake("what if second")

    asyncio.run(dream.background_tick(RecordingAwarenessQueue()))
    asyncio.run(dream.background_tick(RecordingAwarenessQueue()))

    assert dream.state.log[0].associations == [1]
    assert dream.state.log[1].associations == [0]


def test_items_outside_association_window_not_associated_with_new_items():
    from coordinators.dream import ASSOCIATION_WINDOW

    dream = _dream()
    for index in range(ASSOCIATION_WINDOW + 1):
        dream.intake(f"maybe idea {index}")

    asyncio.run(dream.background_tick(RecordingAwarenessQueue()))

    assert dream.state.log[0].associations == []
    assert 0 not in dream.state.log[-1].associations


# background_tick() - decay

def test_decay_fn_is_called_during_background_tick():
    calls = []
    dream = _dream(decay_fn=lambda: calls.append("decayed"))

    asyncio.run(dream.background_tick(RecordingAwarenessQueue()))

    assert calls == ["decayed"]


def test_decay_fn_none_is_no_error():
    dream = _dream(decay_fn=None)

    asyncio.run(dream.background_tick(RecordingAwarenessQueue()))

    assert dream.state.idle_decay_cycles == 1


def test_idle_decay_cycles_increments_by_one_per_tick():
    dream = _dream()

    asyncio.run(dream.background_tick(RecordingAwarenessQueue()))
    asyncio.run(dream.background_tick(RecordingAwarenessQueue()))

    assert dream.state.idle_decay_cycles == 2


# background_tick() - Awareness bids

def test_awareness_queue_put_nowait_not_called_during_background_tick():
    queue = RecordingAwarenessQueue()
    dream = _dream()
    dream.intake("maybe")

    asyncio.run(dream.background_tick(queue))

    assert queue.put_items == []


def test_awareness_queue_submit_receives_nrem_summary_during_background_tick():
    queue = RecordingAwarenessQueue()
    dream = _dream()
    dream.intake("maybe")

    asyncio.run(dream.background_tick(queue))

    assert len(queue.submitted) == 1
    bid = queue.submitted[0]
    assert bid.coordinator_name == "dream"
    assert "NREM complete" in bid.content


# process()

def test_process_attaches_dream_log_size_key():
    packet = _dream().process({})

    assert "dream_log_size" in packet


def test_dream_log_size_reflects_current_log_length():
    dream = _dream()
    dream.intake("first")
    dream.intake("second")

    packet = dream.process({})

    assert packet["dream_log_size"] == 2


def test_process_does_not_modify_other_packet_keys():
    dream = _dream()
    packet = {"message": "leave this"}

    result = dream.process(packet)

    assert result["message"] == "leave this"


# brain_loop integration

def test_dream_is_registered_in_default_coordinator_registry():
    from coordinators.brain_loop import BrainLoop
    from coordinators.dream import Dream

    brain_loop = BrainLoop()

    assert isinstance(brain_loop.coordinators["dream"], Dream)
    assert brain_loop.intervals["dream"] == 300.0


def test_dream_background_tick_has_standard_signature_without_mirror_queue():
    from coordinators.brain_loop import _accepts_mirror_queue

    assert _accepts_mirror_queue(_dream()) is False
