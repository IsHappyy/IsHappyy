"""Stage 6 - time and price. Code only, no AI.

Ported from the tpt-machining-quote skill's scripts/estimate.py so it can be
imported. tests/test_price.py holds it to the original's output baht for baht -
change the model in one place and update the parity fixture on purpose, never
by accident.
"""
from __future__ import annotations

import json
import math

from . import CONFIG

OPS = ["drill", "drill_deep", "ream", "counterbore", "tap_small", "tap_large",
       "countersink", "bore_circular"]
BAND = (0.85, 1.20)


def load_profile(path=None) -> dict:
    with open(path or CONFIG / "shop_profile.json", encoding="utf-8") as f:
        return json.load(f)


def one(part: dict, P: dict) -> dict:
    T = P["time_min"]
    K = P["shop_calibration_K"]
    mat = part.get("material", "AL")
    mult = P["material_multiplier"].get(mat, 1.0)
    tol = P["tolerance_multiplier"].get(part.get("tolerance", "general"), 1.0)
    shape = P["shape_multiplier"].get(part.get("shape", "rect"), 1.0)
    qty = int(part.get("qty", 1))
    t = float(part.get("t", 10))
    L = float(part.get("L", 100))
    W = float(part.get("W", 60))
    lathe = bool(part.get("lathe", False))
    ops = {k: float(part.get("ops", {}).get(k, 0)) for k in OPS}
    ops["slot_mm"] = float(part.get("ops", {}).get("slot_mm", 0))
    ops["pocket_cm3"] = float(part.get("ops", {}).get("pocket_cm3", 0))
    hole_circ = float(part.get("hole_circumference_mm", 0))

    perim = math.pi * W if lathe else 2 * (L + W) * shape
    edge = perim * 2 + hole_circ * 2
    n_types = sum(1 for k in OPS if ops[k] > 0) + 2
    n_types = max(3, n_types)

    if lathe:
        cut = (T["lathe_base"] + T["lathe_per_10mm_dia"] * W / 10
               + ops["drill"] * T["drill"] + ops["drill_deep"] * T["drill_deep"]
               + ops["ream"] * T["ream"] + ops["counterbore"] * T["counterbore"]
               + ops["tap_small"] * T["tap_small"] + ops["tap_large"] * T["tap_large"]
               + ops["bore_circular"] * T["bore_circular"])
    else:
        cut = (perim / 100 * T["profile_per_100mm_per_10mm_depth"] * (t / 10)
               + ops["drill"] * T["drill"] + ops["drill_deep"] * T["drill_deep"]
               + ops["ream"] * T["ream"] + ops["counterbore"] * T["counterbore"]
               + ops["tap_small"] * T["tap_small"] + ops["tap_large"] * T["tap_large"]
               + ops["countersink"] * T["countersink"]
               + ops["bore_circular"] * T["bore_circular"]
               + ops["slot_mm"] / 100 * T["slot_per_100mm"]
               + ops["pocket_cm3"] * T["pocket_per_cm3"]
               + edge / 100 * T["chamfer_per_100mm"]
               + n_types * T["tool_change"])
    cut *= mult * tol

    vol = math.pi * (W / 2) ** 2 * L if lathe else L * W * t
    kg = vol * P["density_g_cm3"].get(mat, 2.66) / 1e6
    b1, b2 = P["load_weight_breaks_kg"]
    load1 = T["load_light"] if kg < b1 else (T["load_medium"] if kg < b2 else T["load_heavy"])
    setups = int(part.get("setups", 1))

    machine = ((cut + load1 * setups) * qty + T["probe_per_setup"] * setups) * K["machine"]
    hand = ((edge / 100 * T["deburr_per_100mm"] * math.sqrt(mult)
             + T["inspect_pack"]) * qty) * K["hand"]
    prog = (T["program_base"] + T["program_per_feature_type"] * n_types
            + T["setup_first"] + T["setup_additional"] * (setups - 1)
            + T["prove_out"]) * K["programming"]

    R = P["rates_per_hour"]
    labour = machine / 60 * R["machine"] + hand / 60 * R["hand"] + prog / 60 * R["programming"]

    kg_stock = kg * (1 + P["stock_allowance_pct"] / 100) * qty
    mat_cost = kg_stock * P["material_price_per_kg"].get(mat, 300)
    area = (math.pi * W * L + 2 * math.pi * (W / 2) ** 2 if lathe
            else 2 * L * W + perim * t) / 1e6 * qty

    return {
        "dwg": part.get("dwg", "?"), "name": part.get("name", ""), "material": mat,
        "t": t, "qty": qty, "setups": setups, "holes": int(sum(ops[k] for k in OPS)),
        "cut_min": round(cut, 1), "machine_min": round(machine, 1),
        "hand_min": round(hand, 1), "prog_min": round(prog, 1),
        "total_min": round(machine + hand + prog, 1),
        "labour": round(labour), "kg": round(kg_stock, 2), "material_cost": round(mat_cost),
        "area_m2": round(area, 4), "finish": part.get("finish", "none"),
        "weight_each_kg": round(kg, 2), "perim_mm": round(perim), "L": L, "W": W,
        "lathe": lathe,
    }


def part_flags(part: dict, r: dict, P: dict) -> list[tuple[str, str]]:
    """The skill's flags(): ("HIGH"|"MED", Thai message)."""
    F = []
    lim = P["machine_limits"]
    if max(r["L"], r["W"]) > lim["max_travel_x_mm"]:
        F.append(("HIGH", f"ขนาด {r['L']:.0f} มม. เกินระยะวิ่ง X ของเครื่อง "
                          f"({lim['max_travel_x_mm']}) — ต้องแบ่งเซ็ตหรือหาเครื่องใหญ่กว่า"))
    if r["weight_each_kg"] > 10:
        F.append(("HIGH", f"ชิ้นหนัก {r['weight_each_kg']} กก. — ต้องมีรอกหรือสองคนยก "
                          f"เวลาใส่ถอดคิดที่ระดับหนักแล้ว"))
    if part.get("tolerance") in ("h7", "pm01"):
        F.append(("HIGH", "มีรูพิกัด H7 หรือ tol ±0.01 — ต้องรีมเมอร์/คว้าน และตรวจ CMM"))
    if r["setups"] > 1:
        F.append(("MED", f"จับงาน {r['setups']} ครั้ง — ยืนยันกับแบบว่ามีงานจากด้านอื่นจริง"))
    if r["holes"] >= 20:
        F.append(("MED", f"รู {r['holes']} รู — เวลาเจาะเป็นก้อนใหญ่ที่สุดของงานนี้"))
    if max(r["L"], r["W"]) <= 45:
        F.append(("HIGH", "ชิ้นเล็กมาก — ต้องคิดวิธีจับก่อน อาจกัดเป็นแพแล้วตัดแยก"))
    if r["t"] and r["t"] <= 2:
        F.append(("HIGH", f"แผ่นบาง t={r['t']} — เสี่ยงบิด ตัดเลเซอร์มักถูกกว่า"))
    if r["qty"] == 1:
        F.append(("MED", "Q'ty 1 — เวลาเตรียมหารไม่ได้ ราคาต่อชิ้นจึงสูง"))
    if part.get("from_scan"):
        F.append(("HIGH", "แบบเป็นภาพสแกน — ทุกตัวเลขมาจากการอ่านด้วยตา ต้องให้คนตรวจซ้ำ"))
    for n in part.get("notes", []):
        F.append(("MED", n))
    return F


def price_parts(parts: list[dict], P: dict | None = None) -> dict:
    """Same result as `estimate.py --json`, plus the suggested band."""
    P = P or load_profile()
    rows = [one(p, P) for p in parts]

    fin_groups: dict[str, float] = {}
    for r in rows:
        if r["finish"] and r["finish"] != "none":
            fin_groups.setdefault(r["finish"], 0.0)
            fin_groups[r["finish"]] += r["area_m2"]
    fin_cost = {}
    for k, area in fin_groups.items():
        cfg = P["finishing"].get(k, {"per_m2": 0, "min_lot": 0})
        fin_cost[k] = max(area * cfg["per_m2"], cfg["min_lot"])
    for r in rows:
        k = r["finish"]
        r["finish_cost"] = round(fin_cost[k] * (r["area_m2"] / fin_groups[k])) \
            if k in fin_cost and fin_groups[k] else 0

    mg = 1 + P["margin_pct"] / 100
    for r in rows:
        r["total"] = round((r["labour"] + r["material_cost"] + r["finish_cost"]) * mg)
        r["each"] = round(r["total"] / r["qty"])

    gt = sum(r["total"] for r in rows)
    return {"parts": rows,
            "finishing_lots": {k: round(v) for k, v in fin_cost.items()},
            "grand_total": gt,
            "band": [round(gt * BAND[0]), round(gt * BAND[1])]}


def format_table(result: dict) -> str:
    rows = result["parts"]
    w = [16, 20, 11, 5, 4, 5, 7, 9, 9, 8, 10, 9]
    hdr = ["Dwg", "ชื่อชิ้น", "วัสดุ", "t", "Q", "set", "นาที", "ค่าแรง",
           "วัสดุ", "ผิว", "รวม", "ต่อชิ้น"]
    out = [" ".join(h.ljust(x)[:x] for h, x in zip(hdr, w)), "-" * (sum(w) + len(w))]
    for r in rows:
        cells = [r["dwg"], r["name"][:20], r["material"], f'{r["t"]:g}', str(r["qty"]),
                 str(r["setups"]), f'{r["total_min"]:.0f}', f'{r["labour"]:,}',
                 f'{r["material_cost"]:,}', f'{r["finish_cost"]:,}',
                 f'{r["total"]:,}', f'{r["each"]:,}']
        out.append(" ".join(str(c).ljust(x)[:x] for c, x in zip(cells, w)))
    out.append("-" * (sum(w) + len(w)))
    out.append(f'รวม {len(rows)} ชิ้น · '
               f'เครื่อง {sum(r["machine_min"] for r in rows)/60:.1f} ชม. · '
               f'มือ {sum(r["hand_min"] for r in rows)/60:.1f} · '
               f'เตรียม {sum(r["prog_min"] for r in rows)/60:.1f} · '
               f'รวมทั้งสิ้น {result["grand_total"]:,} บาท')
    lo, hi = result["band"]
    out.append(f"ช่วงที่ควรเสนอ {lo:,} – {hi:,} บาท")
    return "\n".join(out)


def offer(cost: float, risk_pct: float, markup_pct: float, offered: float | None = None) -> dict:
    """Cost -> suggested quote -> profit.

    cost       = estimate total with margin_pct removed (the shop's real cost)
    suggested  = cost x (1 + risk%) x (1 + markup%), rounded up to 10 baht
    profit_pct = profit / offered price (margin on the selling price)
    """
    suggested = math.ceil(cost * (1 + risk_pct / 100) * (1 + markup_pct / 100) / 10) * 10
    price = suggested if offered is None else offered
    profit = price - cost
    return {"cost": round(cost), "risk_pct": risk_pct, "markup_pct": markup_pct,
            "suggested": suggested, "offered": round(price),
            "profit": round(profit),
            "profit_pct": round(profit / price * 100, 1) if price else None,
            "markup_on_cost_pct": round(profit / cost * 100, 1) if cost else None}
