"""End to end on a synthetic Pioneer-style vector PDF, no API calls."""
import json

from pipeline.run import check, run
from pipeline.s1_ingest import ingest
from pipeline.s2_vector import extract
from pipeline.s3_assemble import from_vector
from pipeline.schemas import Evidence, QuoteSpec


def test_ingest_classifies_and_guesses_template(vector_pdf):
    info = ingest(vector_pdf)
    assert info["verdict"] == "VECTOR"
    assert info["template_guess"]["template"] == "Pioneer"


def test_vector_extract_reads_title_block_and_tag_table(vector_pdf):
    v = extract(vector_pdf)
    assert v["drawing_no"] == "TK-2638-01"
    assert v["material_key"] == "STEEL_MILD" and v["thickness_mm"] == 12
    assert v["qty"] == 2 and v["finishing_text"] == "BLACK OXIDE"
    assert v["tolerance_class"] == "h7"
    groups = {g["letter"]: g for g in v["hole_groups"]}
    assert groups["A"]["tags"] == ["A1", "A2", "A3", "A4"]
    assert groups["A"]["feature"]["cbore"] == [11.0, 6.5]
    assert groups["B"]["feature"]["tap"] == 6.0 and groups["B"]["feature"]["blind"]
    assert groups["C"]["feature"]["ream"]
    assert v["size_candidates_mm"][:2] == [200.0, 150.0]


def test_quotespec_from_vector(vector_pdf):
    s = from_vector(extract(vector_pdf))
    assert (s.material, s.t, s.qty, s.finish, s.tolerance) == ("STEEL_MILD", 12, 2, "black_oxide", "h7")
    o = s.ops
    assert (o.drill, o.counterbore, o.tap_small, o.ream) == (8, 4, 2, 2)
    assert s.setups == 2 and s.evidence["setups"].source == "rule"
    assert s.evidence["L"].confidence == "low"


def test_blocks_until_human_confirms_then_prices(vector_pdf):
    s = from_vector(extract(vector_pdf))
    first = check(s)
    assert first["price"] is None
    assert {f["field"] for f in first["flags"] if f["level"] == "block"} >= {"L", "W"}

    for f in ("L", "W", "setups", "tolerance"):
        s.evidence[f] = Evidence(source="human")
    done = check(QuoteSpec.model_validate(s.model_dump()))
    assert done["price"] is not None and done["price"]["grand_total"] > 0
    assert not [f for f in done["flags"] if f["level"] == "block"]


def test_run_writes_every_stage(vector_pdf, tmp_path):
    out = run(vector_pdf, out_root=tmp_path / "runs", vector_only=True)
    for name in ("manifest.json", "ingest.json", "vector.json", "quotespec.ai.json",
                 "check.ai.json", "page.png", "text_layer.txt"):
        assert (out / name).is_file(), name
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert man["mode"] == "vector-only" and len(man["input_sha256"]) == 64
