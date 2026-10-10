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
