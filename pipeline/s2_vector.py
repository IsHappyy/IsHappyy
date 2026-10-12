"""Stage 2a - read a VECTOR PDF from its text layer. Code only, exact numbers.

Ported from the skill's scripts/parse_vector.py. Two additions: every tag-table
group keeps its tag names (so tag joins can be done in code), and the output is
plain data for s3_assemble to turn into QuoteSpec fields with evidence.

KNOWN LIMIT: diameter / counterbore / depth symbols are drawn as vector paths by
SolidWorks and are missing from the text layer. Numbers survive, symbols do not.
That gap is what the vision reader is for - not re-reading numbers code already has.
"""
from __future__ import annotations

import re
from pathlib import Path

import pymupdf

COUNT_RE = re.compile(r"(?<![\d.A-Za-z])(\d{1,3})\s*[xX](?!\s*\d{1,3}\s*(?:°|deg))")
ANGLE_ONLY_RE = re.compile(r"^\s*\d{1,3}\s*[xX]\s*\d{1,3}\s*(?:°|deg)\s*$")
DEG_RE = re.compile(r"°|deg")

MATDB = [
    (r"A5\d{3}|A6\d{3}|A2\d{3}|ALUMI|AL\b", "AL"),
    (r"SUS\s*\d{3}|STAINLESS|SS3\d{2}", "SUS"),
    (r"SKD|SKS|SKH|HPM|NAK|HARDEN", "STEEL_TOOL"),
    (r"SS41|SS400|S\d{2}C|SPCC|SPHC|ST37|Q235|MILD", "STEEL_MILD"),
    (r"BRASS|C3604|BSBM", "BRASS"),
    (r"PVC|MC\d|POM|PEEK|NYLON|ESD|DELRIN|UHMW", "PLASTIC"),
]


def words_of(page) -> list[dict]:
    return [{"x": round(w[0], 1), "y": round(w[1], 1), "x2": round(w[2], 1), "s": w[4]}
            for w in page.get_text("words")]


def cell(ws, labels, pad=6, dy=22):
    a = [w for w in ws if w["s"] in labels]
    if not a:
        return "", []
    lx = min(w["x"] for w in a)
    rx = max(w["x2"] for w in a)
    ly = min(w["y"] for w in a)
    got = [w for w in ws if ly - dy < w["y"] < ly - 3
           and not (w["x2"] < lx - pad or w["x"] > rx + pad)]
    got.sort(key=lambda w: w["x"])
    return " ".join(w["s"] for w in got), got


def material_key(s: str) -> str | None:
    for rx, k in MATDB:
        if re.search(rx, s, re.I):
            return k
    return None


def parse_size(t: str) -> dict:
    """One SIZE-column / callout string -> feature dict."""
    # no4-style text layer: the font maps Ø->"P", counterbore->"X", depth->"Z", and
    # THRU wraps onto its own line ("P4.90 | THRU", "X P6.50 Z | 3.00")
    cb = re.search(r"\bX\s*P?\s*([\d.]+)\s*Z\s*\|?\s*([\d.]+)", t)
    t = re.sub(r"\bP(?=\d)", "", t)
    t = re.sub(r"\s*\|\s*THRU", " THRU", t, flags=re.I)
    if cb:
        t = t[:t.find("X")].rstrip(" |") if "X" in t else t
    f = {"thru": None, "tap": None, "tap_pitch": None, "cbore": None,
         "csk": False, "bore": None, "blind": False, "ream": False, "depth": None,
         "far_side": bool(re.search(r"FAR\s*SIDE", t, re.I))}
    m = re.search(r"([\d.]+)\s*THRU", t, re.I)
    if m:
        f["thru"] = float(m.group(1))
    m = re.search(r"M\s*([\d.]+)\s*[xX]\s*([\d.]+)", t)
    if m:
        f["tap"] = float(m.group(1))
        f["tap_pitch"] = float(m.group(2))
        tail = t[m.start():m.start() + 40].upper()
        if "THRU" not in tail:
            d = re.search(r"6H\s*[^\d]*([\d.]+)", tail)
            if d:  # blind only when a depth is called out; "M4x0.7 - 6H" alone = through
                f["depth"] = float(d.group(1))
                f["blind"] = True
    if cb:
        f["cbore"] = [float(cb.group(1)), float(cb.group(2))]
    if re.search(r"[xX]\s*90", t):
        f["csk"] = True
    if re.search(r"\bH[67]\b|\bREAM|\bG[67]\b", t, re.I):
        f["ream"] = True
    for seg in [s.strip() for s in t.split("|")]:
        if (re.search(r"THRU", seg, re.I) or re.search(r"M\s*[\d.]+\s*x", seg)
                or DEG_RE.search(seg) or "90" in seg):
            continue
        n = re.findall(r"[\d.]+", seg)
        if len(n) == 2:
            f["cbore"] = [float(n[0]), float(n[1])]
        elif len(n) == 1 and not f["thru"] and float(n[0]) > 8:
            f["bore"] = float(n[0])
    return f


def tag_table(ws):
    # header cell: TAG (no3 style) or HOLE (no4 style, "HOLE | XDIM | YDIM | DESCRIPTION");
    # pick the one sharing a row with the size column header, not the "HOLE TABLE" title
    sizes = [w for w in ws if w["s"] in ("SIZE", "DESCRIPTION")]
    heads = [w for w in ws if w["s"] in ("TAG", "HOLE")
             and any(abs(w["y"] - z["y"]) < 5 for z in sizes)]
    hdr = heads[0] if heads else next((w for w in ws if w["s"] == "TAG"), None)
    if not hdr:
        return None
    tags = sorted([w for w in ws
                   if w["y"] > hdr["y"] + 3 and abs(w["x"] - hdr["x"]) < 48
                   and re.fullmatch(r"[A-Z]\d{1,2}", w["s"])],
                  key=lambda w: w["y"])
    if len(tags) < 3:
        return None
    y_end = tags[-1]["y"] + 22
    sz = next((w for w in ws if w["s"] in ("SIZE", "DESCRIPTION") and abs(w["y"] - hdr["y"]) < 5), None)
    sx = (sz["x"] - 80) if sz else hdr["x"] + 150
    if sz:  # never reach back into the Y column (no4: YDIM sits 56pt left of DESCRIPTION)
        row = [w for w in ws if abs(w["y"] - hdr["y"]) < 5 and w["x"] < sz["x"]]
        if row:
            sx = max(sx, max(w["x2"] for w in row) + 2)

    rows: dict[int, list] = {}
    for w in ws:
        if w["x"] > sx and hdr["y"] + 5 < w["y"] < y_end:
            rows.setdefault(round(w["y"]), []).append(w)
    ys = sorted(rows)
    blocks, cur = [], []
    for y in ys:
        if cur and y - cur[-1] > 20:
            blocks.append(cur)
            cur = []
        cur.append(y)
    if cur:
        blocks.append(cur)

    texts = []
    for b in blocks:
        t = " | ".join(" ".join(x["s"] for x in sorted(rows[y], key=lambda z: z["x"]))
                       for y in b)
        if re.search(r"\d", t) and not re.search(
                r"Dwg|Sheet|MATERIAL|X LOC|SCALE|Q'TY|ISO 1", t, re.I):
            texts.append(t)

    order, by_letter = [], {}
    for t in tags:
        L = t["s"][0]
        if L not in by_letter:
            by_letter[L] = []
            order.append(L)
        by_letter[L].append(t["s"])

    groups = []
    for i, L in enumerate(order):
        raw = texts[i] if i < len(texts) else ""
        groups.append({"source": "tag_table", "letter": L, "count": len(by_letter[L]),
                       "tags": by_letter[L], "raw": raw, "feature": parse_size(raw)})
    claimed = {id(t) for t in tags}
    for b in blocks:
        for y in b:
            for w in rows[y]:
                claimed.add(id(w))
    return {"groups": groups, "claimed": claimed,
            "bbox": {"x1": min(hdr["x"], sx), "y1": hdr["y"] - 10, "y2": y_end}}


def callouts(lines):
    """Leader callouts on drawings without a TAG table (2-3 stacked lines per hole)."""
    out, used = [], set()
    for i, ln in enumerate(lines):
        if i in used:
            continue
        s = ln["s"]
        if not re.search(r"THRU|M\s*[\d.]+\s*[xX]\s*[\d.]+", s, re.I):
            continue
        if ANGLE_ONLY_RE.match(s):
            continue
        win = [j for j in (i - 1, i, i + 1) if 0 <= j < len(lines) and j not in used]
        parts, claimed = [], []
        for j in win:
            txt = lines[j]["s"]
            if j != i and ANGLE_ONLY_RE.match(txt):
                continue
            if j == i - 1 and not re.search(r"[\d.]+", txt):
                continue
            if j == i + 1 and not re.search(r"M\s*[\d.]+|THRU|^[\d.\s]+$", txt, re.I):
                continue
            parts.append(txt)
            claimed += lines[j]["ws"]
            used.add(j)
        ctx = " | ".join(parts)
        f = parse_size(ctx)
        if not f["thru"] and not f["tap"]:
            continue
        n = 1
        for seg in parts:
            m = COUNT_RE.search(seg)
            if m:
                n = int(m.group(1))
                break
        out.append({"source": "callout", "letter": "-", "count": n, "tags": [],
                    "raw": ctx.strip(), "feature": f, "_ws": claimed})
    return out


def extract(path: str | Path) -> dict:
    doc = pymupdf.open(path)
    page = doc[0]
    ws = words_of(page)
    buckets: dict[int, list] = {}
    for w in ws:
        buckets.setdefault(round(w["y"] / 3), []).append(w)
    lines = []
    for k in sorted(buckets):
        row = sorted(buckets[k], key=lambda w: w["x"])
        lines.append({"ws": row, "s": " ".join(w["s"] for w in row)})
    text = "\n".join(l["s"] for l in lines)

    claimed = set()
    mat_t, mat_ws = cell(ws, ["MATERIAL", "MATREIAL", "METERIAL"])
    fin_t, fin_ws = cell(ws, ["FINISHING"])
    qty_t, qty_ws = cell(ws, ["Q'TY", "QTY"])
    nam_t, nam_ws = cell(ws, ["PART", "NAME"], pad=30)
    for g in (mat_ws, fin_ws, qty_ws, nam_ws):
        claimed |= {id(w) for w in g}

    material = re.split(r"\st\s*=|Ø|\bL\s*=", mat_t)[0].strip()
    thick = re.search(r"t\s*=\s*([\d.]+)", text)
    bar_d = re.search(r"[ØΦ⌀]\s*([\d.]+)", text)
    bar_l = re.search(r"L\s*=\s*([\d.]+)", text)
    dwg = re.search(r"\b[A-Z]{2,5}[-_]?\d{3,6}[-_]\d{1,3}\s?[A-Z]?\b", text)

    tt = tag_table(ws)
    if tt:
        groups = tt["groups"]
        claimed |= tt["claimed"]
        tbox = tt["bbox"]
    else:
        groups = []
        for c in callouts(lines):
            claimed |= {id(w) for w in c.pop("_ws")}
            groups.append(c)
        tbox = None

    cands = []
    for w in ws:
        if id(w) in claimed or not re.fullmatch(r"\d{2,4}(\.\d+)?", w["s"]):
            continue
        if tbox and w["x"] > tbox["x1"] - 40 and tbox["y1"] < w["y"] < tbox["y2"]:
            continue
        v = float(w["s"])
        if 15 <= v <= 2000 and not (1990 <= v <= 2100):
            cands.append(v)
    size_candidates = sorted(set(cands), reverse=True)[:6]

    unmatched = sorted({w["s"] for w in ws
                        if id(w) not in claimed and re.search(r"\d", w["s"])
                        and len(w["s"]) >= 2})

    tol = "general"
    if re.search(r"\bH[67]\b|±\s*0\.0[12]", text):
        tol = "h7"
    elif re.search(r"±\s*0\.05|\.xx\s*0?\.05", text):
        tol = "pm05"
    if re.search(r"±\s*0\.01\b", text):
        tol = "pm01"

    return {
        "file": Path(path).name,
        "drawing_no": dwg.group(0).strip() if dwg else None,  # regex can swallow a trailing \s
        "part_name": re.sub(r"\d+/\d+/\d{2,4}", "", nam_t).strip() or None,
        "material_text": material or None,
        "material_key": material_key(material or ""),
        "finishing_text": fin_t.strip() or None,
        "qty": int(qty_t) if qty_t.strip().isdigit() else None,
        "thickness_mm": float(thick.group(1)) if thick else None,
        "bar_dia_mm": float(bar_d.group(1)) if bar_d else None,
        "bar_len_mm": float(bar_l.group(1)) if bar_l else None,
        "tolerance_class": tol,
        "has_revision_block": bool(re.search(r"REVISIONS?\s+HISTORY", text, re.I)),
        "read_path": "tag_table" if tt else "callout",
        "table_bbox": tt["bbox"] if tt else None,
        "hole_groups": groups,
        "size_candidates_mm": size_candidates,
        "unmatched_numbers": unmatched[:60],
        "unmatched_count": len(unmatched),
    }
