"""Tests for PromptToQuery translation with injected LM."""

from dspy.utils import DummyLM

from api_gateway.routes.leads import translate_prompt


def test_translate_prompt_uses_injected_lm() -> None:
    lm = DummyLM(answers=[{"target_query": "dental clinic Warsaw"}])

    result = translate_prompt("find dentists in Warsaw", lm=lm)

    assert result == "dental clinic Warsaw"
    assert len(lm.history) == 1
