"""Stage 2b - vision readers, using YOUR prompts from prompts/.

The readers' JSON shape is defined by the prompts themselves (feature_reader.md,
table_reader.md, ...), so outputs are stored raw and s3_assemble.from_partspec
maps them. Each call goes through llm.call_json: real API, prompt sha logged,
cached under runs/_cache by (prompt sha, model, effort, image bytes).

What to send is deliberately simple - full page + overlapping tiles + the text
layer as hints. If your crop-by-zone code works better, replace `build_content`.
"""
from __future__ import annotations

import json

from . import llm
from .prompts import exists, load_prompt
from .s1_ingest import fit_png, tiles

READERS = ["title_reader", "feature_reader", "table_reader"]
RECONCILER = "reconciler"


def build_content(page_png: bytes, info: dict, grid: tuple[int, int] = (2, 2)) -> list[dict]:
    blocks = [llm.text_block("ภาพย่อทั้งแผ่น (ใช้ดูตำแหน่งเท่านั้น):"),
              llm.image_block(fit_png(page_png, 1600))]
    for i, t in enumerate(tiles(page_png, *grid)):
        blocks += [llm.text_block(f"tile {i + 1}/{grid[0] * grid[1]} (ซ้อนกัน 10%):"),
                   llm.image_block(t)]
    hints = {
        "file": info.get("file"),
        "file_type": info.get("verdict"),
        "template_guess_by_code": (info.get("template_guess") or {}).get("template"),
        "text_layer": (info.get("text") or "")[:6000] or None,
    }
    blocks.append(llm.text_block("ข้อมูลประกอบจากโค้ด (text layer ถูกต้องตามตัวอักษร แต่ไม่มีสัญลักษณ์):\n"
                                 + json.dumps(hints, ensure_ascii=False)))
    return blocks


def run_readers(page_png: bytes, info: dict, *, use_cache: bool = True,
                readers: list[str] | None = None) -> dict:
    """Run every reader prompt that exists; then the reconciler if it exists.

    Returns {"outputs": {name: json}, "meta": {name: meta}, "skipped": [names]}.
    """
    content = build_content(page_png, info)
    outputs, metas, skipped = {}, {}, []
    for name in readers or READERS:
        if not exists(name):
            skipped.append(name)
            continue
        data, meta = llm.call_json(load_prompt(name), content, use_cache=use_cache)
        outputs[name], metas[name] = data, meta

    if exists(RECONCILER) and {"feature_reader", "table_reader"} <= outputs.keys():
        # reconciler.md stops and asks unless the pair is named explicitly
        payload = llm.text_block(
            f"คู่ไฟล์ที่ต้อง reconcile (ยืนยันแล้วว่าเป็นชิ้นงานเดียวกัน: {info.get('file')}):\n"
            "แหล่งที่ 1 feature_reading.json:\n"
            + json.dumps(outputs["feature_reader"], ensure_ascii=False)
            + "\n\nแหล่งที่ 2 table_reading.json:\n"
            + json.dumps(outputs["table_reader"], ensure_ascii=False))
        data, meta = llm.call_json(load_prompt(RECONCILER),
                                   [llm.image_block(fit_png(page_png, 1600)), payload],
                                   use_cache=use_cache)
        outputs[RECONCILER], metas[RECONCILER] = data, meta
    elif not exists(RECONCILER):
        skipped.append(RECONCILER)
    return {"outputs": outputs, "meta": metas, "skipped": skipped}
