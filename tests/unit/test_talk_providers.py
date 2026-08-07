"""talk_providers tests (PRD_4 §2.5, §3). enforce_word_cap is the single
shared helper both the template and every LLM path run through -- an LLM
cannot be trusted to self-limit, so the cap is deterministic and applied
identically regardless of source (PRD_4 §4)."""

import random

from thief_peer.strategy.talk_providers import TemplateProvider, enforce_word_cap


def test_template_provider_returns_a_generic_phrase_when_no_map_area():
    provider = TemplateProvider(rng=random.Random(0))
    line = provider.generate()

    assert isinstance(line, str)
    assert len(line) > 0
    assert "{" not in line  # no unfilled format placeholder leaked through


def test_template_provider_references_the_configured_map_area():
    provider = TemplateProvider(rng=random.Random(0))
    line = provider.generate(map_area="New York")

    assert "New York" in line


def test_template_provider_is_deterministic_given_the_same_rng_seed():
    a = TemplateProvider(rng=random.Random(42)).generate(map_area="Paris")
    b = TemplateProvider(rng=random.Random(42)).generate(map_area="Paris")

    assert a == b


def test_enforce_word_cap_leaves_short_text_untouched():
    text = "I am nowhere near you"
    assert enforce_word_cap(text, max_words=15) == text


def test_enforce_word_cap_truncates_text_over_the_limit():
    text = "one two three four five six seven eight"
    capped = enforce_word_cap(text, max_words=3)

    assert capped == "one two three"
    assert len(capped.split()) == 3


def test_enforce_word_cap_applies_identically_regardless_of_source():
    # Same helper, same behaviour, whether the text came from the template
    # or an LLM -- there is only one code path to test (PRD_4 §4).
    template_text = "one two three four five six"
    llm_text = "one two three four five six"

    assert enforce_word_cap(template_text, 3) == enforce_word_cap(llm_text, 3)
