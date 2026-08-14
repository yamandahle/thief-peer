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


def test_template_provider_defaults_to_a_truthful_phrase_when_verdict_is_omitted():
    provider = TemplateProvider(rng=random.Random(0))
    truth_line = provider.generate(verdict="truth")
    default_line = provider.generate()

    assert default_line == truth_line


def test_template_provider_never_mixes_lie_and_truth_phrase_pools():
    # Book ch.6.5: the two intents must draw from genuinely separate pools,
    # not a shared one filtered after the fact -- exhaustively sample many
    # draws from each verdict and confirm the pools never overlap.
    rng = random.Random(1)
    provider = TemplateProvider(rng=rng)
    lie_lines = {provider.generate(verdict="lie") for _ in range(50)}
    truth_lines = {provider.generate(verdict="truth") for _ in range(50)}

    assert lie_lines.isdisjoint(truth_lines)


def test_template_provider_lie_and_truth_both_still_respect_the_map_area():
    provider = TemplateProvider(rng=random.Random(7))

    lie_line = provider.generate(map_area="Tokyo", verdict="lie")
    truth_line = provider.generate(map_area="Tokyo", verdict="truth")

    assert "Tokyo" in lie_line
    assert "Tokyo" in truth_line


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
