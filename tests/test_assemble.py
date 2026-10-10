from pipeline.s3_assemble import (finish_key, from_partspec, join_by_tag, merge,
                                  ops_for_hole)
from pipeline.schemas import Evidence, Ops, QuoteSpec


def test_tap_needs_its_drill_and_blind_tap_suggests_setup():
    ops, circ, notes, setup = ops_for_hole({"count": 2, "tap": 6, "tap_pitch": 1.0, "blind": True,
                                            "depth": 12, "raw": "M6x1.0 - 6H 12"})
    assert (ops.drill, ops.tap_small, ops.tap_large) == (2, 2, 0)
    assert notes == []
    assert setup and setup[0].startswith("เกลียวตัน")


def test_large_and_fine_and_unknown_threads():
    ops, _, notes, _ = ops_for_hole({"count": 1, "tap": 12, "tap_pitch": 1.25})
    assert ops.tap_large == 1 and "เกลียวละเอียด" in notes[0]
    ops, _, notes, _ = ops_for_hole({"count": 1, "tap": 20})
    assert ops.tap_large == 1 and "ไม่อยู่ในตาราง" in notes[0]


def test_h7_counts_drill_and_ream_deep_hole_pecks():
    ops, _, _, _ = ops_for_hole({"count": 4, "thru": 8.0, "ream": True})
    assert (ops.drill, ops.ream) == (4, 4)
    ops, _, _, setup = ops_for_hole({"count": 1, "dia": 5, "depth": 20})
    assert ops.drill_deep == 1 and ops.drill == 0
    assert setup and setup[0].startswith("รูตัน")


def test_counterbore_and_countersink_and_bore():
    ops, circ, _, _ = ops_for_hole({"count": 3, "thru": 6.6, "cbore": [11, 6.5]})
    assert (ops.drill, ops.counterbore) == (3, 3)
    assert round(circ, 1) == round(3.141592653589793 * 11 * 3, 1)
    ops, _, _, _ = ops_for_hole({"count": 2, "thru": 4.5, "csk": True})
    assert ops.countersink == 2
    ops, _, _, _ = ops_for_hole({"count": 1, "bore": 38})
    assert ops.bore_circular == 1 and ops.drill == 0


def test_vision_thru_flag_is_not_read_as_a_diameter():
    ops, circ, _, setup = ops_for_hole({"count": 1, "thru": True, "dia": 10, "depth": 50})
    assert ops.drill_deep == 1  # 50 > 3 x 10, diameter must come from dia, not from True
    assert setup == []


def test_from_partspec_maps_known_types_and_keeps_unknown_as_leftovers():
    ps = {
        "title": {"material_raw": "A5052", "quantity": "3", "part_number": "TK-2667-02"},
        "features": [
            {"feature_type": "tapped_hole", "count": 4, "size": {"thread": "M5x0.8", "depth": 10}},
            {"feature_type": "through_hole", "tags": ["A1", "A2"], "size": {"diameter": 6.6, "thru": True}},
            {"feature_type": "chamfer", "size": {"raw": "C0.5"}},
            {"feature_type": "pocket", "count": 1, "size": {"length": 40, "width": 20, "depth": 5}},
            {"feature_type": "hatch_legend_zone", "raw_text": "สีแดง = ลึก 3"},
        ],
    }
    spec = from_partspec(ps)
    assert spec.material == "AL" and spec.qty == 3 and spec.dwg == "TK-2667-02"
    assert (spec.ops.drill, spec.ops.tap_small) == (6, 4)
    assert spec.ops.pocket_cm3 == 4.0
    assert len(spec.leftovers) == 1 and spec.leftovers[0]["why"] == "ไม่รู้จัก feature_type"
    assert spec.setups == 2  # blind taps -> suggests a second face
    assert spec.evidence["setups"].confidence == "low"


def test_join_by_tag():
    j = join_by_tag([{"tag": "A1"}, {"tag": "a 2"}, {"tag": "B1"}],
                    [{"tag": "A1"}, {"tag": "A2"}, {"tag": "C1"}])
    assert [m[0]["tag"] for m in j["matched"]] == ["A1", "a 2"]
    assert [x["tag"] for x in j["only_left"]] == ["B1"]
    assert [x["tag"] for x in j["only_right"]] == ["C1"]


def test_merge_text_layer_wins_and_disagreements_become_conflicts():
    a = QuoteSpec(material="STEEL_MILD", qty=2, ops=Ops(drill=8),
                  evidence={"material": Evidence(source="text_layer"), "qty": Evidence(source="text_layer")})
    b = QuoteSpec(material="SUS", qty=2, t=12, ops=Ops(drill=6), lathe=False,
                  evidence={"material": Evidence(source="vision"), "t": Evidence(source="vision")})
    m = merge(a, b)
    assert m.material == "STEEL_MILD" and m.t == 12
    assert m.ops.drill == 8  # never summed
    assert any(c.startswith("material") for c in m.conflicts)
    assert any("drill 8≠6" in c for c in m.conflicts)


def test_merge_ignores_formatting_differences():
    ev = Evidence(source="text_layer")
    a = QuoteSpec(dwg="TK-2638-01", material_raw="SS400", evidence={"dwg": ev, "material_raw": ev})
    b = QuoteSpec(dwg="TK 2638 01", material_raw="SS-400 t=12",
                  evidence={"dwg": Evidence(source="vision"), "material_raw": Evidence(source="vision")})
    assert merge(a, b).conflicts == []


def test_finish_key():
    assert finish_key("BLACK OXIDE") == "black_oxide"
    assert finish_key("Anodize clear") == "anodize"
    assert finish_key("-") == "none"
    assert finish_key("HRC 58-60") is None
