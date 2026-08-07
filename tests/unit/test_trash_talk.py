"""TrashTalk tests (PRD_4 §2.5, §2.6, §3, §5). The LLM path must be
genuinely bounded -- a stub that hangs past the deadline must still let the
turn complete on time, not just "usually work" (PRD_4 §5's LLM timeout
acceptance criterion)."""

import time

import pytest

from thief_peer.strategy.talk_providers import TemplateProvider
from thief_peer.strategy.trash_talk import TrashTalk, choose_verdict


class _FixedTemplate(TemplateProvider):
    def __init__(self):
        pass

    def generate(self, map_area: str = "") -> str:
        return "template line"


class _StubLlm:
    def __init__(self, text="llm line", raises=None, sleep_seconds=0.0):
        self._text = text
        self._raises = raises
        self._sleep_seconds = sleep_seconds
        self.calls = 0

    def generate(self, map_area: str = "") -> str:
        self.calls += 1
        if self._sleep_seconds:
            time.sleep(self._sleep_seconds)
        if self._raises:
            raise self._raises
        return self._text


def test_uses_template_when_no_llm_provider_configured():
    talk = TrashTalk(_FixedTemplate(), llm_provider=None, every_n_steps=1)
    assert talk.generate_hint(step=1) == "template line"


def test_uses_llm_on_matching_steps():
    llm = _StubLlm(text="llm line")
    talk = TrashTalk(_FixedTemplate(), llm_provider=llm, every_n_steps=3)

    assert talk.generate_hint(step=3) == "llm line"
    assert llm.calls == 1


def test_uses_template_on_steps_not_matching_every_n_steps():
    llm = _StubLlm(text="llm line")
    talk = TrashTalk(_FixedTemplate(), llm_provider=llm, every_n_steps=3)

    assert talk.generate_hint(step=1) == "template line"
    assert talk.generate_hint(step=2) == "template line"
    assert llm.calls == 0


def test_every_n_steps_3_over_9_turns_calls_llm_exactly_3_times():
    llm = _StubLlm(text="llm line")
    talk = TrashTalk(_FixedTemplate(), llm_provider=llm, every_n_steps=3)

    for step in range(1, 10):
        talk.generate_hint(step=step)

    assert llm.calls == 3


def test_falls_back_to_template_when_llm_raises():
    llm = _StubLlm(raises=RuntimeError("boom"))
    talk = TrashTalk(_FixedTemplate(), llm_provider=llm, every_n_steps=1)

    assert talk.generate_hint(step=1) == "template line"


def test_falls_back_to_template_and_stays_bounded_when_llm_exceeds_deadline():
    llm = _StubLlm(text="too slow", sleep_seconds=2.0)
    talk = TrashTalk(
        _FixedTemplate(), llm_provider=llm, every_n_steps=1, step_deadline_seconds=0.2
    )

    start = time.monotonic()
    result = talk.generate_hint(step=1)
    elapsed = time.monotonic() - start

    assert result == "template line"
    assert elapsed < 1.0  # bounded by the deadline, not by the stub's 2s sleep


def test_hint_is_word_capped_regardless_of_source():
    class _LongTemplate(TemplateProvider):
        def __init__(self):
            pass

        def generate(self, map_area: str = "") -> str:
            return "one two three four five six seven eight nine ten eleven"

    talk = TrashTalk(_LongTemplate(), llm_provider=None, every_n_steps=1, hint_max_words=3)
    assert talk.generate_hint(step=1) == "one two three"


def test_choose_verdict_prefers_lie_when_belief_is_already_close():
    # small expected_distance relative to the board -> belief is accurate
    assert choose_verdict(expected_distance=1.0, max_possible_distance=20.0) == "lie"


def test_choose_verdict_prefers_truth_when_belief_is_far_off():
    assert choose_verdict(expected_distance=18.0, max_possible_distance=20.0) == "truth"


@pytest.mark.parametrize("expected_distance", [0.0, 20.0])
def test_choose_verdict_never_raises_at_the_extremes(expected_distance):
    choose_verdict(expected_distance=expected_distance, max_possible_distance=20.0)
