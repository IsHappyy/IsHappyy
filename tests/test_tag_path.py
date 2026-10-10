"""Pioneer path: table masked, tags joined in code, reconciler only for leftovers."""
import io
import json

from PIL import Image

from pipeline import llm, s2_vision
from pipeline.run import run


def fake_call(seen_tags, calls):
    def call_json(prompt, content, **kw):
        calls.append(prompt.name)
        if prompt.name == "feature_reader":
            return {"visible_tags": seen_tags, "note": None}, {"prompt_sha": "x", "model_served": "m",
                                                              "cache": "miss"}
        return {"part_features": [], "unmatched_tags": []}, {"prompt_sha": "y", "model_served": "m",
                                                             "cache": "miss"}
    return call_json


def test_all_tags_match_no_reconciler_call(vector_pdf, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "call_json",
                        fake_call(["A1", "A2", "A3", "A4", "B1", "B2", "C1", "C2"], calls))
    out = run(vector_pdf, out_root=tmp_path / "runs")
    v = json.loads((out / "vision.json").read_text(encoding="utf-8"))
    assert calls == ["feature_reader"]
    assert v["tag_join"] == {"matched": 8, "only_feature": [], "only_table": []}
    spec = json.loads((out / "quotespec.ai.json").read_text(encoding="utf-8"))
    assert spec["leftovers"] == [] and spec["ops"]["drill"] == 8


def test_missing_tag_goes_to_reconciler_and_blocks(vector_pdf, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "call_json", fake_call(["A1", "A2", "A3", "A4", "B1", "C1", "C2", "Z9"], calls))
    out = run(vector_pdf, out_root=tmp_path / "runs")
    v = json.loads((out / "vision.json").read_text(encoding="utf-8"))
    assert calls == ["feature_reader", "reconciler"]
    assert v["tag_join"]["only_table"] == ["B2"] and v["tag_join"]["only_feature"] == ["Z9"]
    chk = json.loads((out / "check.ai.json").read_text(encoding="utf-8"))
    assert chk["price"] is None
    assert sum(f["code"] == "leftover" for f in chk["flags"]) == 2


def test_mask_blanks_table_region():
    im = Image.new("RGB", (842, 595), "black")
    buf = io.BytesIO(); im.save(buf, "PNG")
    out = Image.open(io.BytesIO(s2_vision.mask_region(buf.getvalue(), [842, 595],
                                                       {"x1": 500, "y1": 50, "y2": 170})))
    assert out.getpixel((700, 100)) == (255, 255, 255)   # table area
    assert out.getpixel((100, 400)) == (0, 0, 0)         # drawing untouched
