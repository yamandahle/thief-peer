"""llm_provider tests (PRD_4 §2.5, §3). One common interface so
trash_talk.py never branches on provider type. `claude_api`/`claude_cli` are
interface-only in this stage -- wiring a live, rate-limit-unprotected paid
API before Stage 7's Gatekeeper exists is exactly the kind of scaffolding
this project has learned (Stage 2's rule-27 carve-out) is dangerous to leave
lying around."""

import pytest

from thief_peer.exceptions import ProviderError
from thief_peer.infra.llm_provider import (
    ClaudeApiProvider,
    ClaudeCliProvider,
    LlmProvider,
    OllamaProvider,
)


def test_llm_provider_base_defines_the_common_generate_signature():
    import inspect

    params = inspect.signature(LlmProvider.generate).parameters
    assert "map_area" in params


def test_ollama_provider_returns_the_calls_text_on_success(monkeypatch):
    provider = OllamaProvider()
    monkeypatch.setattr(provider, "_call", lambda prompt: "the trail is cold")

    result = provider.generate(map_area="Paris")

    assert result == "the trail is cold"


def test_ollama_provider_prompt_includes_the_map_area():
    provider = OllamaProvider()
    prompt = provider._build_prompt(map_area="Paris", verdict="truth")

    assert "Paris" in prompt


def test_ollama_provider_prompt_differs_between_lie_and_truth_verdicts():
    # Book ch.6.5: a lie round's prompt must actually ask for something
    # misleading, not the same instruction regardless of intent.
    provider = OllamaProvider()
    lie_prompt = provider._build_prompt(map_area="Paris", verdict="lie")
    truth_prompt = provider._build_prompt(map_area="Paris", verdict="truth")

    assert lie_prompt != truth_prompt
    assert "misleading" in lie_prompt
    assert "honest" in truth_prompt


def test_ollama_provider_wraps_call_failures_in_provider_error(monkeypatch):
    provider = OllamaProvider()

    def _boom(prompt):
        raise ConnectionError("no local server")

    monkeypatch.setattr(provider, "_call", _boom)

    with pytest.raises(ProviderError):
        provider.generate()


def test_claude_api_provider_is_interface_only_for_now():
    provider = ClaudeApiProvider(api_key="dummy")
    with pytest.raises(ProviderError, match="Gatekeeper"):
        provider.generate()


def test_claude_cli_provider_is_interface_only_for_now():
    provider = ClaudeCliProvider()
    with pytest.raises(ProviderError, match="Gatekeeper"):
        provider.generate()


def test_all_providers_share_the_same_generate_signature():
    import inspect

    base_params = list(inspect.signature(LlmProvider.generate).parameters)
    for cls in (OllamaProvider, ClaudeApiProvider, ClaudeCliProvider):
        assert list(inspect.signature(cls.generate).parameters) == base_params
