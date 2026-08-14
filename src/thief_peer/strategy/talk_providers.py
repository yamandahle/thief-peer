"""Hint-generation providers (PRD_4 §2.5, §3). `TemplateProvider` is the
zero-token, zero-latency default the book recommends; `enforce_word_cap` is
the single shared helper both the template and every LLM path run through,
since an LLM cannot be trusted to self-limit (same reasoning as ADR-1).

Book ch.6.5: the verbal layer's job is to compose a "plausible but
misleading" hint on a lie round, but say something that doesn't actively
mislead on a truth round -- two separate phrase sets below, picked by
`verdict` (`strategy.trash_talk.choose_verdict`'s own output), not one
canned pool regardless of intent (PRD_4's original gap).
"""

import random

_LIE_PHRASES_GENERIC = [
    "I'm nowhere near where you think I am.",
    "The trail runs cold from here.",
    "You're chasing a ghost.",
    "I doubled back a while ago.",
    "Keep looking, you're not close.",
]
_LIE_PHRASES_WITH_LANDMARK = [
    "Last seen heading toward {landmark}.",
    "I slipped past {landmark} a few turns back.",
    "Ask anyone near {landmark} -- they haven't seen me.",
]
_TRUTH_PHRASES_GENERIC = [
    "I'll admit, you're not far off.",
    "You're actually closer than you'd think.",
    "Keep going -- you're on the right track.",
    "No point denying it, you're closing in.",
]
_TRUTH_PHRASES_WITH_LANDMARK = [
    "I'm still not far from {landmark}, actually.",
    "You're right to check around {landmark}.",
    "Yeah, {landmark} rings a bell -- I was just there.",
]


class TemplateProvider:
    def __init__(self, rng: random.Random | None = None):
        self._rng = rng or random.Random()

    def generate(self, map_area: str = "", verdict: str = "truth") -> str:
        if verdict == "lie":
            phrases = _LIE_PHRASES_WITH_LANDMARK if map_area else _LIE_PHRASES_GENERIC
        else:
            phrases = _TRUTH_PHRASES_WITH_LANDMARK if map_area else _TRUTH_PHRASES_GENERIC
        phrase = self._rng.choice(phrases)
        return phrase.format(landmark=map_area) if map_area else phrase


def enforce_word_cap(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])
