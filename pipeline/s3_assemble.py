"""Stage 3 - turn readings into one QuoteSpec. Code only.

Everything here is a fixed rule, so it lives in code rather than in a prompt:
  - counting ops per hole (a tap needs its drill, an H7 hole needs drill + ream)
  - joining two readings by tag
  - merging text-layer and vision readings, and recording where they disagree
  - suggesting a setup count (always low confidence until a human confirms)

The AI reconciler is only needed for what these rules cannot place; those
features land in `leftovers` and block the quote until a human decides.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

from . import CONFIG
from .s2_vector import material_key, parse_size
from .schemas import Evidence, Ops, QuoteSpec

HEADER_FIELDS = ["dwg", "name", "material", "material_raw", "t", "L", "W", "qty",
                 "tolerance", "finish", "lathe"]
FILL_ONLY = {"name", "material_raw"}  # free text: differences are formatting, not facts


def _same(a, b) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return re.sub(r"[\s\-_.]", "", a).upper() == re.sub(r"[\s\-_.]", "", b).upper()
    return a == b


def load_tap_table() -> dict:
    with open(CONFIG / "tap_drill.json", encoding="utf-8") as f:
        return json.load(f)["threads"]


def load_feature_map() -> dict[str, str]:
    """feature_type alias -> kind. `edge_direction` is a modifier, not a kind."""
    with open(CONFIG / "feature_map.json", encoding="utf-8") as f:
        raw = json.load(f)
    out = {}
    for kind, names in raw.items():
        if kind.startswith("_") or kind == "edge_direction":
            continue
        for n in names:
            out.setdefault(n.lower(), kind)
    out["__edge__"] = ",".join(n.lower() for n in raw.get("edge_direction", []))
    return out


def finish_key(text: str | None) -> str | None:
    if not text:
        return None
    t = text.upper()
    if re.search(r"ANOD|ALUMITE|อโนไดซ์", t):
        return "anodize"
    if re.search(r"BLACK|OXIDE|รมดำ", t):
        return "black_oxide"
    if re.search(r"ZINC|\bZN\b|ชุบซิงค์|ซิงค์", t):
        return "zinc_plate"
    if re.fullmatch(r"\s*(-+|NONE|NIL|N/?A|NO)\s*", t):
        return "none"
    return None


# ---------------------------------------------------------------- holes -> ops

def ops_for_hole(h: dict, tap_table: dict | None = None) -> tuple[Ops, float, list[str], list[str]]:
    """One hole callout (count + attributes) -> (ops, circumference_mm, notes, setup_reasons).

    h keys (all optional except count): count, dia, thru, depth, tap, tap_pitch, blind,
    ream, cbore [dia, depth], csk, bore, edge, raw.
    """
    tap_table = tap_table or load_tap_table()
    n = int(h.get("count") or 1)
    ops = Ops()
    notes: list[str] = []
    setup: list[str] = []
    raw = h.get("raw") or ""
    circ_d = 0.0

    if h.get("tap"):
        size = h["tap"]
        key = f"M{size:g}"
        row = tap_table.get(key)
        ops.drill += n
        if row:
            setattr(ops, row["class"], getattr(ops, row["class"]) + n)
            if h.get("tap_pitch") and abs(h["tap_pitch"] - row["pitch"]) > 1e-6:
                notes.append(f"{key}x{h['tap_pitch']:g} เป็นเกลียวละเอียด — ต้องใช้ดอกต๊าปพิเศษ ({raw})")
        else:
            cls = "tap_large" if size >= 10 else "tap_small"
            setattr(ops, cls, getattr(ops, cls) + n)
            notes.append(f"เกลียว {key} ไม่อยู่ในตาราง tap drill — ตรวจขนาดดอก ({raw})")
        circ_d = size
        if h.get("blind"):
            setup.append(f"เกลียวตัน {n}× {key} ({raw})")
    elif h.get("bore") and not h.get("thru"):
        ops.bore_circular += n
        circ_d = h["bore"]
    else:
        thru = h.get("thru")  # the vector parser stores the THRU diameter here, vision a bool
        d = thru if isinstance(thru, (int, float)) and not isinstance(thru, bool) else h.get("dia")
        depth = h.get("depth")
        if d and depth and depth > 3 * d:
            ops.drill_deep += n
        else:
            ops.drill += n
        if h.get("ream"):
            ops.ream += n
        circ_d = d or 0.0
        if depth and not thru:
            setup.append(f"รูตัน {n}× ⌀{d or '?'} ลึก {depth:g} ({raw})")

    if h.get("cbore"):
        ops.counterbore += n
        circ_d = max(circ_d, h["cbore"][0])
    if h.get("csk"):
        ops.countersink += n
    if h.get("far_side"):
        setup.append(f"งานด้านตรงข้าม (Far Side) {n}× ({raw})")
    if h.get("edge"):
        setup.append(f"รูด้านข้าง {n}× ({raw})")
    return ops, math.pi * circ_d * n, notes, setup


def suggest_setups(reasons: list[str]) -> tuple[int, str]:
    """1 setup, +1 for blind holes (usually a 2nd face), +1 for side/edge holes."""
    blind = any(r.startswith(("เกลียวตัน", "รูตัน")) for r in reasons)
    edge = any(r.startswith("รูด้านข้าง") for r in reasons)
    far = any(r.startswith("งานด้านตรงข้าม") for r in reasons)
    n = 1 + int(blind or far) + int(edge)
    why = "; ".join(reasons) if reasons else "ไม่พบงานจากด้านอื่น"
    return n, why


def _apply_holes(spec: QuoteSpec, holes: list[dict], tap_table: dict, source: str) -> None:
    total, circ, reasons, raws = Ops(), 0.0, [], []
    for h in holes:
        ops, c, notes, setup = ops_for_hole(h, tap_table)
        total = total.add(ops)
        circ += c
        spec.notes += notes
        reasons += setup
        raws.append(f"{h.get('count', 1)}× {h.get('raw', '')}".strip())
    spec.ops = total
    spec.hole_circumference_mm = round(circ, 1)
    spec.evidence["ops"] = Evidence(source=source, raw_text=" / ".join(raws) or None,
                                    confidence="high" if source == "text_layer" else "medium")
    spec.setups, why = suggest_setups(reasons)
    spec.evidence["setups"] = Evidence(source="rule", confidence="low", note=why)


# ---------------------------------------------------------------- vector path

def from_vector(vec: dict, tap_table: dict | None = None) -> QuoteSpec:
    tap_table = tap_table or load_tap_table()
    spec = QuoteSpec()
    tl = "text_layer"

    def put(field, value, raw=None, conf="high", note=None):
        if value is None:
            return
        setattr(spec, field, value)
        spec.evidence[field] = Evidence(source=tl, raw_text=raw, confidence=conf, note=note)

    put("dwg", vec.get("drawing_no"), vec.get("drawing_no"))
    put("name", vec.get("part_name"), vec.get("part_name"))
    put("material_raw", vec.get("material_text"), vec.get("material_text"))
    put("material", vec.get("material_key"), vec.get("material_text"))
    put("qty", vec.get("qty"), str(vec.get("qty")))
    put("finish", finish_key(vec.get("finishing_text")), vec.get("finishing_text"))
    put("tolerance", vec.get("tolerance_class"), conf="medium",
        note="เดาจากข้อความ H7/±0.0x ในแบบ ไม่ได้อ่านตาราง general tolerance")

    if vec.get("bar_dia_mm"):
        d = vec["bar_dia_mm"]
        put("lathe", True, f"Ø{d:g}", conf="medium")
        put("W", d, f"Ø{d:g}", conf="medium")
        put("t", d, f"Ø{d:g}", conf="medium")
        put("L", vec.get("bar_len_mm"), f"L={vec.get('bar_len_mm')}", conf="medium")
    else:
        put("t", vec.get("thickness_mm"), f"t={vec.get('thickness_mm')}")
        cands = vec.get("size_candidates_mm") or []
        if len(cands) >= 2:
            note = "เลือกตัวเลขใหญ่สุด 2 ตัวจาก dimension — ต้องยืนยันกับภาพ"
            put("L", cands[0], str(cands[0]), conf="low", note=note)
            put("W", cands[1], str(cands[1]), conf="low", note=note)

    holes = []
    for g in vec.get("hole_groups", []):
        h = dict(g["feature"])
        h["count"] = g["count"]
        h["raw"] = f"{g.get('letter', '-')}: {g['raw']}"
        holes.append(h)
    _apply_holes(spec, holes, tap_table, tl)
    return spec


# ---------------------------------------------------------------- vision path

def _get(d: Any, *paths: str):
    """First non-empty value among dotted paths, e.g. _get(f, "size.diameter", "dia")."""
    for p in paths:
        cur = d
        for part in p.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                cur = None
                break
        if cur not in (None, "", []):
            return cur
    return None


def _num(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"\d+(?:\.\d+)?", v)
        return float(m.group(0)) if m else None
    return None


def _thread(v) -> tuple[float | None, float | None]:
    if not v:
        return None, None
    m = re.search(r"M\s*(\d+(?:\.\d+)?)(?:\s*[xX×]\s*(\d+(?:\.\d+)?))?", str(v))
    if not m:
        return None, None
    return float(m.group(1)), (float(m.group(2)) if m.group(2) else None)


def hole_from_feature(f: dict, edge_types: set[str]) -> dict:
    """Map one reconciled feature (PartSpec style) to the hole dict ops_for_hole reads.

    CHECK the key names below against the `size` schema in prompts/reconciler.md -
    this is the one function to adjust when the reconciler output changes.
    """
    ftype = str(_get(f, "feature_type", "type") or "").lower()
    raw = str(_get(f, "raw_description", "raw_text", "callout", "size.raw") or "")
    parsed = parse_size(raw.replace("⌀", "").replace("Ø", ""))  # text facts the size{} may omit
    tags = _get(f, "tags", "source_tags") or ([f["tag"]] if f.get("tag") else [])
    count = _get(f, "count", "multiplier", "quantity", "qty") or (len(tags) if len(tags) > 1 else 1)
    tap, pitch = _thread(_get(f, "size.thread", "thread", "size.thread_spec") or raw)
    thru_flag = (_get(f, "size.thru", "thru", "size.through") is True
                 or ftype == "through_hole" or bool(parsed["thru"]))
    dia = _num(_get(f, "size.dia", "size.diameter", "size.drill_diameter", "diameter", "dia")) \
        or parsed["thru"]
    depth = _num(_get(f, "size.depth", "depth", "size.thread_depth")) or parsed["depth"]
    fit = str(_get(f, "size.fit", "fit", "size.tolerance", "tolerance") or "") + " " + raw
    cb_d = _num(_get(f, "size.cbore_dia", "size.cbore_diameter", "size.counterbore.diameter",
                     "cbore_diameter"))
    cb_h = _num(_get(f, "size.cbore_depth", "size.counterbore.depth", "cbore_depth"))
    if ftype in ("counterbore", "cbore", "spotface") and not cb_d:
        cb_d, cb_h = dia, depth
    csk = (ftype in ("countersink", "csk")
           or bool(_get(f, "size.csk_dia", "size.csk_angle", "size.countersink", "size.csk")))
    return {
        "count": int(_num(count) or 1), "dia": dia, "depth": depth,
        "thru": True if thru_flag else None,
        "tap": tap, "tap_pitch": pitch, "blind": bool(tap) and not thru_flag,
        "ream": bool(re.search(r"\b[HG][67]\b", fit)),
        "cbore": [cb_d, cb_h or 0] if cb_d else None,
        "csk": csk,
        "far_side": bool(re.search(r"FAR\s*SIDE", raw, re.I)),
        "edge": ftype in edge_types or str(_get(f, "face", "direction") or "").lower() in ("side", "edge"),
        "raw": raw or ftype,
    }


def from_partspec(ps: dict, feature_map: dict | None = None,
                  tap_table: dict | None = None) -> QuoteSpec:
    """Reconciled PartSpec JSON (from the vision readers) -> QuoteSpec.

    Unknown feature types and pockets/slots without the numbers needed to price
    them go to `leftovers`; nothing is dropped silently.
    """
    fmap = feature_map or load_feature_map()
    tap_table = tap_table or load_tap_table()
    edge_types = set(filter(None, fmap.get("__edge__", "").split(",")))
    spec = QuoteSpec()

    title = _get(ps, "title", "title_block", "header", "part") or {}
    raw_mat = _get(title, "material_raw", "material")
    fields = {
        "dwg": _get(title, "drawing_number", "part_number", "dwg_no", "dwg"),
        "name": _get(title, "part_name", "name"),
        "material_raw": raw_mat,
        "material": material_key(str(raw_mat)) if raw_mat else None,
        "qty": _get(title, "quantity", "qty"),
        "t": _num(_get(title, "thickness", "t")),
        "finish": finish_key(_get(title, "finish", "finishing", "surface_treatment")),
    }
    for k, v in fields.items():
        if v is None:
            continue
        if k == "qty":
            v = int(_num(v) or 0) or None
            if v is None:
                continue
        setattr(spec, k, v)
        spec.evidence[k] = Evidence(source="vision", raw_text=str(v), confidence="medium")

    holes, ignored = [], 0
    for f in _get(ps, "features", "merged_features", "part_features") or []:
        ftype = str(_get(f, "feature_type", "type") or "").lower()
        kind = fmap.get(ftype)
        if kind in ("hole", "tapped_hole", "counterbore", "countersink"):
            holes.append(hole_from_feature(f, edge_types))
        elif kind == "no_op":
            ignored += 1
        elif kind == "lathe":
            spec.lathe = True
            spec.evidence["lathe"] = Evidence(source="vision", raw_text=ftype, confidence="medium")
        elif kind == "slot" and _num(_get(f, "size.length", "length")):
            spec.ops.slot_mm += _num(_get(f, "size.length", "length")) * int(_get(f, "count") or 1)
        elif kind == "pocket" and all(_num(_get(f, f"size.{k}", k)) for k in ("length", "width", "depth")):
            l, w, d = (_num(_get(f, f"size.{k}", k)) for k in ("length", "width", "depth"))
            spec.ops.pocket_cm3 += l * w * d / 1000 * int(_get(f, "count") or 1)
        else:
            spec.leftovers.append({"why": "ไม่รู้จัก feature_type" if kind is None
                                   else f"{kind} ขาดขนาดที่ใช้คิดราคา", "feature": f})

    slot, pocket = spec.ops.slot_mm, spec.ops.pocket_cm3
    _apply_holes(spec, holes, tap_table, "vision")
    spec.ops.slot_mm, spec.ops.pocket_cm3 = slot, pocket
    if ignored:
        spec.evidence["ops"].note = f"ไม่คิด chamfer/fillet {ignored} จุด (รวมในเวลา deburr แล้ว)"
    for u in _get(ps, "unmatched_tags", "unmatched", "unmatched_features") or []:
        spec.leftovers.append({"why": "reconciler จับคู่ tag ไม่ได้", "feature": u})
    for u in _get(ps, "other_features_without_tag") or []:
        spec.leftovers.append({"why": "feature ไม่มี tag — คนต้องตัดสินจำนวน/ว่าคิดราคาไหม",
                               "feature": u})
    for n in _get(ps, "reconciler_notes.per_part") or []:
        if n not in spec.notes:
            spec.notes.append(str(n))
    return spec


# ---------------------------------------------------------------- joins and merges

def join_by_tag(left: list[dict], right: list[dict], key: str = "tag") -> dict:
    """Deterministic join (what the AI reconciler was doing for tagged holes)."""
    norm = lambda s: re.sub(r"\s+", "", str(s)).upper()
    L = {norm(x[key]): x for x in left if x.get(key)}
    R = {norm(x[key]): x for x in right if x.get(key)}
    return {"matched": [(L[k], R[k]) for k in sorted(L.keys() & R.keys())],
            "only_left": [L[k] for k in sorted(L.keys() - R.keys())],
            "only_right": [R[k] for k in sorted(R.keys() - L.keys())]}


def merge(primary: QuoteSpec, secondary: QuoteSpec) -> QuoteSpec:
    """Primary (text layer) wins on header facts; secondary (vision) fills gaps.

    Ops are never added together - that would double-count every hole. They come
    from the primary when it has any, and a different total is recorded as a
    conflict for the human to settle.
    """
    out = primary.model_copy(deep=True)
    for f in HEADER_FIELDS:
        a, b = getattr(primary, f), getattr(secondary, f)
        default = QuoteSpec.model_fields[f].default
        if b is None or b == default:
            continue
        if a is None or (a == default and f not in primary.evidence):
            setattr(out, f, b)
            if f in secondary.evidence:
                out.evidence[f] = secondary.evidence[f]
        elif (f not in FILL_ONLY and not _same(a, b)
              and f in primary.evidence and f in secondary.evidence):
            out.conflicts.append(f"{f}: text layer = {a!r}, vision = {b!r}")

    pa, pb = primary.ops.model_dump(), secondary.ops.model_dump()
    if not any(pa.values()):
        out.ops = secondary.ops.model_copy()
        out.hole_circumference_mm = secondary.hole_circumference_mm
        if "ops" in secondary.evidence:
            out.evidence["ops"] = secondary.evidence["ops"]
    else:
        diff = {k: (pa[k], pb[k]) for k in pa if pa[k] != pb[k] and any(pb.values())}
        if diff:
            out.conflicts.append("จำนวน op ไม่ตรงกัน (text layer, vision): " +
                                 ", ".join(f"{k} {a:g}≠{b:g}" for k, (a, b) in diff.items()))
        out.ops.slot_mm = out.ops.slot_mm or secondary.ops.slot_mm
        out.ops.pocket_cm3 = out.ops.pocket_cm3 or secondary.ops.pocket_cm3

    if secondary.setups > out.setups and "setups" in secondary.evidence:
        out.setups = secondary.setups
        out.evidence["setups"] = secondary.evidence["setups"]
    out.leftovers += secondary.leftovers
    out.conflicts += secondary.conflicts
    out.notes += [n for n in secondary.notes if n not in out.notes]
    return out
