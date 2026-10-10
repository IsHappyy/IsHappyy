"""llm.call_json with a fake client: no network, no key."""
from types import SimpleNamespace

import pytest

from pipeline import llm
from pipeline.prompts import Prompt, load_prompt, sha12


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def _reply(self, **kw):
        self.calls.append(kw)
        text, stop = self.replies.pop(0)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)], stop_reason=stop,
            model="served-model", _request_id="req_1", parsed_output=None,
            usage=SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0))

    create = _reply
    parse = _reply


def fake_client(replies):
    return SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages(replies)))


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_READ", "test-model")
    monkeypatch.setenv("LLM_FALLBACKS", "default")
    return tmp_path / "cache"


P = Prompt(name="feature_reader", text="read the drawing", sha=sha12("read the drawing"), path=None)


def test_retries_bad_json_then_caches(env):
    c = fake_client([("not json", "end_turn"), ('```json\n{"features": []}\n```', "end_turn")])
    data, meta = llm.call_json(P, [llm.text_block("x")], client=c, cache_dir=env)
    assert data == {"features": []}
    assert meta["attempts"] == 2 and meta["prompt_sha"] == P.sha
    assert meta["model_served"] == "served-model" and meta["cache"] == "miss"
    sent = c.beta.messages.calls[0]
    assert "temperature" not in sent
    assert sent["fallbacks"] == "default" and sent["betas"] == [llm.FALLBACK_BETA]
    assert sent["system"][0]["text"] == "read the drawing"

    again, meta2 = llm.call_json(P, [llm.text_block("x")], client=fake_client([]), cache_dir=env)
    assert again == data and meta2["cache"] == "hit"


def test_refusal_raises(env):
    c = fake_client([("", "refusal")])
    with pytest.raises(llm.LLMRefusal):
        llm.call_json(P, [llm.text_block("y")], client=c, cache_dir=env, use_cache=False)


def test_missing_model_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("MODEL_READ", raising=False)
    with pytest.raises(llm.LLMError, match="MODEL_READ"):
        llm.call_json(P, [llm.text_block("z")], client=fake_client([]))


def test_prompt_sha_ignores_line_endings_and_missing_prompt_is_explicit(tmp_path):
    (tmp_path / "a.md").write_bytes(b"line1\r\nline2\r\n")
    assert load_prompt("a", tmp_path).sha == sha12("line1\nline2\n")
    with pytest.raises(FileNotFoundError, match="prompts/"):
        load_prompt("feature_reader", tmp_path)
