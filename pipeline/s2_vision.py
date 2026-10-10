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


# ---------------------------------------------------------------- Pioneer path
# Vector drawing with a TAG table: code already read the table exactly, so the
# feature reader sees the drawing with the table blanked out (it can't re-read
# or mis-read it), tags are joined in code, and the reconciler only gets the
# tags code could not match.

def mask_region(page_png: bytes, page_pt: list, bbox: dict, pad: float = 8) -> bytes:
    """Blank the hole table. bbox is in PDF points; the table runs to the right edge."""
    import io

    from PIL import Image, ImageDraw
    im = Image.open(io.BytesIO(page_png)).convert("RGB")
    k = im.width / page_pt[0]
    ImageDraw.Draw(im).rectangle(
        [max(0, (bbox["x1"] - pad) * k), max(0, (bbox["y1"] - pad) * k),
         im.width, min(im.height, (bbox["y2"] + pad) * k)], fill="white")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def tags_seen(feature_out) -> list[str]:
    if not isinstance(feature_out, dict):
        return []
    tags = list(feature_out.get("visible_tags") or [])
    tags += [f["tag"] for f in feature_out.get("features") or [] if isinstance(f, dict) and f.get("tag")]
    return tags


def run_tag_path(page_png: bytes, info: dict, vec: dict, table_bbox: dict, *,
                 use_cache: bool = True) -> dict:
    from .s3_assemble import join_by_tag

    outputs, metas, skipped = {}, {}, ["table_reader (โค้ดอ่านตารางจาก text layer แล้ว)"]
    masked = mask_region(page_png, info["page_pt"], table_bbox)
    if not exists("feature_reader"):
        return {"outputs": {}, "meta": {}, "skipped": skipped + ["feature_reader"], "tag_join": None}
    data, meta = llm.call_json(load_prompt("feature_reader"), build_content(masked, info),
                               use_cache=use_cache)
    outputs["feature_reader"], metas["feature_reader"] = data, meta

    table_rows = [{"tag": t, "raw_description": g["raw"]}
                  for g in vec.get("hole_groups", []) for t in g.get("tags", [])]
    j = join_by_tag([{"tag": t} for t in tags_seen(data)], table_rows)
    join = {"matched": len(j["matched"]),
            "only_feature": [x["tag"] for x in j["only_left"]],
            "only_table": [x["tag"] for x in j["only_right"]]}

    leftovers = join["only_feature"] + join["only_table"]
    if leftovers and exists(RECONCILER):
        sub = [r for r in table_rows if r["tag"] in join["only_table"]]
        payload = llm.text_block(
            f"คู่ไฟล์ที่ต้อง reconcile (ยืนยันแล้วว่าเป็นชิ้นงานเดียวกัน: {info.get('file')}). "
            f"โค้ดจับคู่ tag ไปแล้ว {join['matched']} ตัว ส่งมาเฉพาะ tag ที่จับคู่ไม่ได้:\n"
            "แหล่งที่ 1 feature_reading.json:\n"
            + json.dumps({"visible_tags": join["only_feature"],
                          "note": (data or {}).get("note") if isinstance(data, dict) else None},
                         ensure_ascii=False)
            + "\n\nแหล่งที่ 2 table_reading.json (อ่านจาก text layer):\n"
            + json.dumps({"rows": sub}, ensure_ascii=False))
        rdata, rmeta = llm.call_json(load_prompt(RECONCILER),
                                     [llm.image_block(fit_png(masked, 1600)), payload],
                                     use_cache=use_cache)
        outputs[RECONCILER], metas[RECONCILER] = rdata, rmeta
    elif not leftovers:
        skipped.append("reconciler (โค้ดจับคู่ tag ครบ)")
    return {"outputs": outputs, "meta": metas, "skipped": skipped, "tag_join": join}
