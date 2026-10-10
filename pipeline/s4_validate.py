"""Stage 4 - deterministic checks. Code only.

Three levels (guide section 6):
  block - no price until a human fixes it
  warn  - priceable, but must be shown next to the price
  info  - context for whoever plans the job

Add a rule here every time a quote goes wrong in the shop.
"""
from __future__ import annotations

from .s6_price import load_profile, one, part_flags
from .schemas import KEY_FIELDS, Flag, QuoteSpec

LABEL = {"material": "วัสดุ", "qty": "จำนวนชิ้น", "t": "ความหนา t", "L": "ความยาว L",
         "W": "ความกว้าง W"}


def risk_premium(spec: QuoteSpec, P: dict) -> dict:
    """Applies shop_profile.risk_premium_pct. Confirming a field (source=human) removes its risk."""
    table = P["risk_premium_pct"]
    items = []

    def unconfirmed(field):
        ev = spec.evidence.get(field)
        return not ev or (ev.source != "human" and ev.confidence != "high")

    if spec.setups and not spec.human_confirmed("setups"):
        items.append(("setup_count_uncertain", table["setup_count_uncertain"]))
    if "tolerance" not in spec.evidence or unconfirmed("tolerance"):
        items.append(("no_tolerance_block", table["no_tolerance_block"]))
    if spec.from_scan:
        items.append(("scanned_drawing", table["scanned_drawing"]))
    if spec.finish is None:
        items.append(("finish_unspecified", table["finish_unspecified"]))
    if unconfirmed("material"):
        items.append(("material_unclear", table["material_unclear"]))
    if spec.qty == 1:
        items.append(("qty_one", table["qty_one"]))
    total = sum(p for _, p in items)
    return {"items": items, "total_pct": total, "cap_pct": table["_cap"],
            "over_cap": total > table["_cap"]}


def validate(spec: QuoteSpec, P: dict | None = None) -> list[Flag]:
    P = P or load_profile()
    flags: list[Flag] = []

    def add(level, code, msg, field=None):
        flags.append(Flag(level=level, code=code, msg=msg, field=field))

    for f in KEY_FIELDS:
        if getattr(spec, f) is None:
            add("block", "missing", f"ไม่พบ{LABEL[f]} — ต้องกรอก", f)
        else:
            ev = spec.evidence.get(f)
            if ev and ev.confidence == "low" and ev.source != "human":
                add("block", "low_confidence",
                    f"{LABEL[f]} = {getattr(spec, f)} ความมั่นใจต่ำ ({ev.note or ev.source}) — ต้องยืนยัน", f)
    if spec.material is None and spec.material_raw:
        add("block", "material_unknown",
            f"วัสดุ '{spec.material_raw}' ไม่อยู่ในฐานข้อมูล ({', '.join(P['material_multiplier'])})",
            "material")
    for i, lo in enumerate(spec.leftovers):
        add("block", "leftover", f"feature ที่ยังไม่ได้คิดราคา #{i + 1}: {lo.get('why')}", "leftovers")
    for c in spec.conflicts:
        add("block", "conflict", f"ขัดกัน: {c}")

    if not spec.human_confirmed("setups"):
        ev = spec.evidence.get("setups")
        add("warn", "setups_assumed",
            f"สมมติ {spec.setups} setup ({ev.note if ev else 'ค่าเริ่มต้น'}) — ยืนยันกับแบบ", "setups")
    if spec.finish is None:
        add("warn", "finish_unspecified", "ไม่ระบุผิวสำเร็จ — คิดเป็นไม่ทำผิว", "finish")

    if all(getattr(spec, f) is not None for f in KEY_FIELDS):
        part = spec.to_part()
        for lvl, msg in part_flags(part, one(part, P), P):
            add("warn", f"shop_{lvl.lower()}", msg)

    risk = risk_premium(spec, P)
    if risk["over_cap"]:
        add("block", "risk_over_cap",
            f"ความเสี่ยงรวม {risk['total_pct']}% เกินเพดาน {risk['cap_pct']}% "
            f"({', '.join(k for k, _ in risk['items'])}) — ยืนยัน field ที่เกี่ยวข้องก่อน หรือให้คนตีราคาเอง")

    order = {"block": 0, "warn": 1, "info": 2}
    return sorted(flags, key=lambda f: order[f.level])


def blocked(flags: list[Flag]) -> bool:
    return any(f.level == "block" for f in flags)
