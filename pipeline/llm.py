"""One way to call Claude: the API, directly.

No Claude Code in the loop, so nothing can quietly swap a model call for a
script. Every call returns (data, meta) and meta carries the prompt sha, the
model actually served, usage and the request id.

Notes on current models:
- `temperature` is not accepted by current models (the request is rejected), so
  stability comes from logging + caching + double-read, not from sampling knobs.
- Thinking depth is set with `output_config.effort` (READ_EFFORT in .env).
- `LLM_FALLBACKS=default` lets the API retry a refused request on the
  recommended fallback model; meta["model_served"] records which model answered.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from . import RUNS
from .prompts import Prompt

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(RuntimeError):
    pass


class LLMRefusal(LLMError):
    pass


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env reader (no extra dependency). Existing env vars win."""
    path = path or Path(__file__).resolve().parent.parent / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def image_block(png: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                        "data": base64.standard_b64encode(png).decode()}}


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def _content_sha(content: list[dict]) -> str:
    h = hashlib.sha256()
    for b in content:
        if b["type"] == "image":
            h.update(b["source"]["data"].encode())
        else:
            h.update(b.get("text", "").encode("utf-8"))
    return h.hexdigest()[:16]


def _extract_json(text: str) -> Any:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return json.loads(t)


def _client():
    import anthropic
    return anthropic.Anthropic()


def call_json(prompt: Prompt, content: list[dict], *, schema: type[BaseModel] | None = None,
              model: str | None = None, effort: str | None = None, retries: int = 2,
              max_tokens: int = 16000, client=None, cache_dir: Path | None = None,
              use_cache: bool = True) -> tuple[Any, dict]:
    """Send `content` (image/text blocks) under `prompt` and get JSON back.

    schema=None  -> the prompt defines its own JSON shape; we parse and retry on bad JSON.
    schema=Model -> structured outputs; the API guarantees the shape, Pydantic validates.
    """
    model = model or os.getenv("MODEL_READ")
    if not model:
        raise LLMError("ยังไม่ได้ตั้ง MODEL_READ ใน .env (ดู .env.example)")
    effort = effort or os.getenv("READ_EFFORT", "high")
    fallbacks = os.getenv("LLM_FALLBACKS", "default").lower() != "off"

    key = hashlib.sha256(json.dumps(
        [prompt.sha, model, effort, _content_sha(content),
         schema.__name__ if schema else None]).encode()).hexdigest()[:24]
    cache_dir = cache_dir or RUNS / "_cache"
    cache_file = cache_dir / f"{prompt.name}-{key}.json"
    if use_cache and cache_file.is_file():
        hit = json.loads(cache_file.read_text(encoding="utf-8"))
        data = schema.model_validate(hit["data"]) if schema else hit["data"]
        return data, {**hit["meta"], "cache": "hit"}

    client = client or _client()
    kwargs: dict[str, Any] = dict(
        model=model, max_tokens=max_tokens,
        system=[{"type": "text", "text": prompt.text, "cache_control": {"type": "ephemeral"}}],
        output_config={"effort": effort},
    )
    if fallbacks:
        kwargs.update(betas=[FALLBACK_BETA], fallbacks="default")

    messages: list[dict] = [{"role": "user", "content": content}]
    last_err = None
    for attempt in range(1, retries + 2):
        if schema is not None:
            resp = client.beta.messages.parse(messages=messages, output_format=schema, **kwargs)
        else:
            resp = client.beta.messages.create(messages=messages, **kwargs)

        if resp.stop_reason == "refusal":
            cat = getattr(getattr(resp, "stop_details", None), "category", None)
            raise LLMRefusal(f"โมเดลปฏิเสธคำขอ (category={cat}) prompt={prompt.name}")
        if resp.stop_reason == "max_tokens":
            raise LLMError(f"คำตอบถูกตัดที่ max_tokens={max_tokens} prompt={prompt.name}")

        text = "".join(b.text for b in resp.content if b.type == "text")
        try:
            if schema is not None:
                data = resp.parsed_output
                if data is None:
                    data = schema.model_validate_json(text)
            else:
                data = _extract_json(text)
            break
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = e
            messages += [{"role": "assistant", "content": resp.content},
                         {"role": "user", "content": f"JSON ไม่ถูกต้อง: {e}. ตอบใหม่ทั้งก้อนเป็น JSON อย่างเดียว"}]
    else:
        raise LLMError(f"ได้ JSON ไม่ถูกต้องหลังลอง {retries + 1} ครั้ง: {last_err}")

    usage = getattr(resp, "usage", None)
    meta = {
        "prompt": prompt.name, "prompt_sha": prompt.sha,
        "model_requested": model, "model_served": getattr(resp, "model", model),
        "effort": effort, "attempts": attempt,
        "request_id": getattr(resp, "_request_id", None),
        "input_sha": _content_sha(content),
        "usage": {
            "input": getattr(usage, "input_tokens", None),
            "output": getattr(usage, "output_tokens", None),
            "cache_read": getattr(usage, "cache_read_input_tokens", None),
        },
        "cache": "miss",
    }
    plain = data.model_dump() if isinstance(data, BaseModel) else data
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({"data": plain, "meta": meta}, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    return data, meta
