"""Thin wrapper around the Claude API used by the research and script steps."""

import json
import os

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
# Server-side fallback: if a safety classifier declines, the API retries on a
# recommended fallback model inside the same call.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_CONTINUATIONS = 5

_client = None


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def ask(system, prompt, *, tools=None, schema=None, effort="high", max_tokens=16000):
    """Send one task to Claude and return its text (or parsed JSON when `schema` is set)."""
    output_config = {"effort": effort}
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": schema}

    kwargs = dict(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        output_config=output_config,
        betas=[FALLBACK_BETA],
        fallbacks="default",
    )
    if tools:
        kwargs["tools"] = tools

    messages = [{"role": "user", "content": prompt}]
    for _ in range(MAX_CONTINUATIONS):
        response = client().beta.messages.create(messages=messages, **kwargs)

        if response.stop_reason == "refusal":
            details = response.stop_details.explanation if response.stop_details else ""
            raise RuntimeError(f"Claude declined this request: {details}")
        if response.stop_reason == "pause_turn":
            # A long web-search turn paused; send it back so Claude continues.
            messages = [messages[0], {"role": "assistant", "content": response.content}]
            continue
        if response.stop_reason == "max_tokens":
            raise RuntimeError("Response hit max_tokens; raise max_tokens and retry")

        text = "".join(b.text for b in response.content if b.type == "text")
        return json.loads(text) if schema is not None else text

    raise RuntimeError("Turn still paused after several continuations")
