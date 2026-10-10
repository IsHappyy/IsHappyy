from pipeline.s4_validate import blocked, risk_premium, validate
from pipeline.s6_price import load_profile
from pipeline.schemas import Evidence, Ops, QuoteSpec

P = load_profile()


def confirmed(**kw):
    ev = {k: Evidence(source="human") for k in
          ("material", "qty", "t", "L", "W", "setups", "tolerance", "finish")}
    base = dict(material="AL", qty=5, t=10, L=200, W=100, finish="none", ops=Ops(drill=4), evidence=ev)
    base.update(kw)
    return QuoteSpec(**base)


def test_human_confirmed_spec_is_priceable():
    flags = validate(confirmed(), P)
    assert not blocked(flags)


def test_missing_key_fields_block():
    flags = validate(confirmed(material=None, qty=None), P)
    codes = {(f.code, f.field) for f in flags if f.level == "block"}
    assert ("missing", "material") in codes and ("missing", "qty") in codes


def test_low_confidence_blocks_until_human():
    s = confirmed(L=605)
    s.evidence["L"] = Evidence(source="text_layer", confidence="low", note="size candidate")
    assert any(f.code == "low_confidence" for f in validate(s, P))
    s.evidence["L"] = Evidence(source="human")
    assert not any(f.code == "low_confidence" for f in validate(s, P))


def test_leftovers_and_conflicts_block():
    s = confirmed(leftovers=[{"why": "x"}], conflicts=["material: a vs b"])
    codes = [f.code for f in validate(s, P) if f.level == "block"]
    assert "leftover" in codes and "conflict" in codes


def test_unknown_material_named():
    s = confirmed(material=None, material_raw="INCONEL 718")
    assert any(f.code == "material_unknown" for f in validate(s, P))


def test_risk_premium_drops_as_fields_are_confirmed():
    raw = QuoteSpec(material="AL", qty=1, t=10, L=100, W=60, from_scan=True,
                    evidence={"material": Evidence(source="vision", confidence="medium")})
    r = risk_premium(raw, P)
    assert r["over_cap"] and r["total_pct"] == 8 + 12 + 10 + 5 + 10 + 15
    assert any(f.code == "risk_over_cap" for f in validate(raw, P))
    done = confirmed(qty=1, from_scan=True)
    r = risk_premium(done, P)
    assert not r["over_cap"] and r["total_pct"] == 10 + 15


def test_shop_flags_come_through_as_warnings():
    s = confirmed(L=605, W=263, tolerance="h7")
    msgs = [f.msg for f in validate(s, P) if f.level == "warn"]
    assert any("เกินระยะวิ่ง" in m for m in msgs)
    assert any("H7" in m for m in msgs)
