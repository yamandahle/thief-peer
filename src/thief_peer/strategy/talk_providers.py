"""Hint-generation providers (PRD_4 §2.5, §3). `TemplateProvider` is the
zero-token, zero-latency default the book recommends; `enforce_word_cap` is
the single shared helper both the template and every LLM path run through,
since an LLM cannot be trusted to self-limit (same reasoning as ADR-1).
"""

import random

_PHRASES_GENERIC = [
    "I'm nowhere near where you think I am.",
    "The trail runs cold from here.",
    "You're chasing a ghost.",
    "I doubled back a while ago.",
    "Keep looking, you're not close.",
]
_PHRASES_WITH_LANDMARK = [
    "Last seen heading toward {landmark}.",
    "I slipped past {landmark} a few turns back.",
    "Ask anyone near {landmark} -- they haven't seen me.",
]


class TemplateProvider:
    def __init__(self, rng: random.Random | None = None):
        self._rng = rng or random.Random()

    def generate(self, map_area: str = "") -> str:
        if map_area:
            return self._rng.choice(_PHRASES_WITH_LANDMARK).format(landmark=map_area)
        return self._rng.choice(_PHRASES_GENERIC)


def enforce_word_cap(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])
