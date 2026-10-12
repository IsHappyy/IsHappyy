"""s6_price must give the same answer as the skill's estimate.py, baht for baht.

The fixture was produced by running the original `estimate.py parts.json --json`.
If you change the cost model on purpose, regenerate it on purpose.
"""
import json
from pathlib import Path

from pipeline.s6_price import format_table, load_profile, price_parts

FIX = Path(__file__).parent / "fixtures"


def test_parity_with_original_estimate():
    parts = json.loads((FIX / "parity_parts.json").read_text(encoding="utf-8"))["parts"]
    expected = json.loads((FIX / "parity_expected.json").read_text(encoding="utf-8"))
    got = price_parts(parts, load_profile())
    assert got["parts"] == expected["parts"]
    assert got["finishing_lots"] == expected["finishing_lots"]
    assert got["grand_total"] == expected["grand_total"] == 16332
    assert got["band"] == [13882, 19598]


def test_table_renders():
    parts = json.loads((FIX / "parity_parts.json").read_text(encoding="utf-8"))["parts"]
    txt = format_table(price_parts(parts))
    assert "รวมทั้งสิ้น 16,332 บาท" in txt
    assert "ช่วงที่ควรเสนอ 13,882 – 19,598 บาท" in txt


def test_offer_cost_markup_and_profit():
    from pipeline.s6_price import offer
    o = offer(1000, risk_pct=10, markup_pct=25)
    assert o["suggested"] == 1380              # 1000 x 1.10 x 1.25 = 1375 -> round up to 1380
    assert o["profit"] == 380 and o["profit_pct"] == 27.5
    lower = offer(1000, 10, 25, offered=900)
    assert lower["profit"] == -100 and lower["profit_pct"] < 0
