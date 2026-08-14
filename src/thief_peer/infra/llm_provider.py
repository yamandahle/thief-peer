"""LLM provider adapters (PRD_4 §2.5, §3): one common interface so
`trash_talk.py` never branches on provider type. Real network calls will be
routed through `shared/gatekeeper.py` once Stage 7 builds it -- until then
`ollama` calls out directly (free, local, no rate-limit exposure), while
`claude_api`/`claude_cli` stay interface-only, since wiring a real paid,
rate-limited API before that safety net exists is exactly the kind of
scaffolding this project has already learned (Stage 2's rule-27 carve-out)
is dangerous to leave lying around.
"""

from thief_peer.exceptions import ProviderError

# Book ch.6.5: the verbal layer's actual job differs by round -- a lie round
# wants "plausible but misleading" (pulls the opponent away from the real
# position); a truth round should stay honest, not just non-committal, so
# `Decision.verdict` (`strategy.trash_talk.choose_verdict`) is fed straight
# into the prompt rather than left for the LLM to guess at.
_LIE_PROMPT_TEMPLATE = (
    "You are the Thief in a pursuit game. Give one short, plausible but "
    "misleading line about your location, meant to pull the Cop away from "
    "where you really are. Area: {map_area}. Stay in character, no more "
    "than a sentence."
)
_TRUTH_PROMPT_TEMPLATE = (
    "You are the Thief in a pursuit game. Give one short, honest line "
    "about your location that does not mislead the Cop. Area: {map_area}. "
    "Stay in character, no more than a sentence."
)


class LlmProvider:
    """Common interface every provider adapter implements."""

    def generate(self, map_area: str = "", verdict: str = "truth") -> str:
        raise NotImplementedError


class OllamaProvider(LlmProvider):
    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3", timeout: float = 30.0):
        self._host = host
        self._model = model
        self._timeout = timeout

    def generate(self, map_area: str = "", verdict: str = "truth") -> str:
        prompt = self._build_prompt(map_area, verdict)
        try:
            return self._call(prompt)
        except Exception as exc:
            raise ProviderError(f"Ollama call failed: {exc}") from exc

    def _build_prompt(self, map_area: str, verdict: str) -> str:
        template = _LIE_PROMPT_TEMPLATE if verdict == "lie" else _TRUTH_PROMPT_TEMPLATE
        return template.format(map_area=map_area or "unspecified")

    def _call(self, prompt: str) -> str:
        import httpx

        response = httpx.post(
            f"{self._host}/api/generate",
            json={"model": self._model, "prompt": prompt, "stream": False},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()["response"].strip()


class ClaudeApiProvider(LlmProvider):
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5"):
        self._api_key = api_key
        self._model = model

    def generate(self, map_area: str = "", verdict: str = "truth") -> str:
        raise ProviderError(
            "claude_api is interface-only until Stage 7's Gatekeeper exists "
            "to rate-limit it (PRD_4 §4) -- use 'template' or 'ollama' for now."
        )


class ClaudeCliProvider(LlmProvider):
    def __init__(self, command: str = "claude"):
        self._command = command

    def generate(self, map_area: str = "", verdict: str = "truth") -> str:
        raise ProviderError(
            "claude_cli is interface-only until Stage 7's Gatekeeper exists "
            "to rate-limit it (PRD_4 §4) -- use 'template' or 'ollama' for now."
        )
