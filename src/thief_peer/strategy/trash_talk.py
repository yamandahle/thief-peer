"""Trash-talk orchestration (PRD_4 §2.5, §2.6, §3): selects a provider,
throttles LLM calls to every_n_steps, and falls back to the template on any
LLM error *or* deadline overrun -- the banter must never stall the turn
(book's explicit resilience requirement). The LLM call runs on a background
thread with a real bounded wait: if it hangs past the deadline we stop
waiting and fall back, we don't just hope it returns quickly.

`gatekeeper` (PRD_10 fix, rules 28/29): every external call this peer makes
must go through the one rate-limited/DOS-protected doorway
(`shared/gatekeeper.py::ApiGatekeeper`) -- `report/report_writer.py`'s Gmail
send already did; this LLM call didn't (`infra/llm_provider.py`'s own
docstring self-documented this as a deferred gap since Stage 4, predating
Stage 7's gatekeeper). Optional and backward-compatible: `gatekeeper=None`
(the default, and every existing caller) calls the provider directly, since
no LLM provider is wired into a real match yet either (`peer/runtime_setup.py`
always passes `llm_provider=None` today) -- this closes the routing gap so
whenever that wiring lands, the gatekeeper is already in the path, not a
second gap to find later.
"""

from concurrent.futures import Future, ThreadPoolExecutor

from thief_peer.strategy.talk_providers import TemplateProvider, enforce_word_cap

_LIE_THRESHOLD = 0.5


class TrashTalk:
    def __init__(
        self,
        template_provider: TemplateProvider,
        llm_provider=None,
        every_n_steps: int = 1,
        hint_max_words: int = 15,
        map_area: str = "",
        step_deadline_seconds: float = 5.0,
        gatekeeper=None,
    ):
        self._template = template_provider
        self._llm = llm_provider
        self._every_n_steps = every_n_steps
        self._hint_max_words = hint_max_words
        self._map_area = map_area
        self._step_deadline_seconds = step_deadline_seconds
        self._gatekeeper = gatekeeper

    def generate_hint(self, step: int) -> str:
        use_llm = (
            self._llm is not None
            and self._every_n_steps > 0
            and step % self._every_n_steps == 0
        )
        text = self._call_llm_bounded() if use_llm else None
        if text is None:
            text = self._template.generate(self._map_area)
        return enforce_word_cap(text, self._hint_max_words)

    def _call_llm(self) -> str:
        if self._gatekeeper is not None:
            return self._gatekeeper.execute(self._llm.generate, self._map_area)
        return self._llm.generate(self._map_area)

    def _call_llm_bounded(self) -> str | None:
        pool = ThreadPoolExecutor(max_workers=1)
        future: Future = pool.submit(self._call_llm)
        try:
            return future.result(timeout=self._step_deadline_seconds)
        except Exception:
            return None
        finally:
            pool.shutdown(wait=False, cancel_futures=True)


def choose_verdict(expected_distance: float, max_possible_distance: float) -> str:
    """Strategic truth/lie bias (PRD_4 §2.6), fed the same `_expected_distance`
    signal `ThiefBrain` already computes for movement -- lying is worth more
    when the opponent's belief is already close (muddying an accurate guess),
    truth costs little when it's already far off. Callers reuse the movement
    computation rather than recomputing it here."""
    if max_possible_distance <= 0:
        return "truth"
    closeness = 1.0 - min(expected_distance / max_possible_distance, 1.0)
    return "lie" if closeness > _LIE_THRESHOLD else "truth"
