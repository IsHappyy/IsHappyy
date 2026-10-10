"""Human checkpoint (stage 5).

    streamlit run app.py

Left: the drawing. Right: the QuoteSpec the pipeline filled in, field by field
with where each value came from. Edit or tick "ยืนยัน", watch the flags and the
price update, then save. Saving writes quotespec.human.json and corrections.json
(AI value vs human value + seconds spent) - the raw material for eval and for
deciding which reading problem to fix next.

"กรอกเอง" mode needs no AI at all, so Summit scans can be quoted with the same
sheet and the same price model from day one.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

from pipeline import RUNS
from pipeline.run import check
from pipeline.s1_ingest import render_png
from pipeline.s6_price import format_table, load_profile
from pipeline.schemas import OP_KEYS, Evidence, Ops, QuoteSpec

st.set_page_config(page_title="TPT ตรวจแบบ + ราคา", layout="wide")
P = load_profile()
MATERIALS = list(P["material_multiplier"])
FIELD_HELP = {"text_layer": "ข้อความในไฟล์ (แม่นตามตัวอักษร)", "vision": "AI อ่านจากภาพ",
              "rule": "กฎในโค้ด (เดา)", "human": "คนยืนยันแล้ว", "default": "ค่าเริ่มต้น"}


def list_runs() -> list[Path]:
    if not RUNS.is_dir():
        return []
    runs = [p for p in RUNS.iterdir() if (p / "quotespec.ai.json").is_file()]
    return sorted(runs, key=lambda p: p.stat().st_mtime, reverse=True)


def ev_caption(ev: Evidence | None) -> str:
    if not ev:
        return "ไม่มีหลักฐาน"
    parts = [FIELD_HELP.get(ev.source, ev.source)]
    if ev.confidence:
        parts.append(f"มั่นใจ {ev.confidence}")
    if ev.raw_text:
        parts.append(f"«{ev.raw_text[:80]}»")
    if ev.note:
        parts.append(ev.note)
    return " · ".join(parts)


# ---------------------------------------------------------------- choose input
mode = st.sidebar.radio("โหมด", ["เปิดผลจาก pipeline", "กรอกเอง (ไม่มี AI)"])
run_dir: Path | None = None
page_png: bytes | None = None
if mode == "เปิดผลจาก pipeline":
    runs = list_runs()
    if not runs:
        st.info("ยังไม่มีผลใน runs/ — รัน `python -m pipeline.run samples/<file>.pdf` ก่อน หรือใช้โหมดกรอกเอง")
        st.stop()
    run_dir = st.sidebar.selectbox("ผลการรัน", runs, format_func=lambda p: p.name)
    ai = QuoteSpec.model_validate_json((run_dir / "quotespec.ai.json").read_text(encoding="utf-8"))
    if (run_dir / "page.png").is_file():
        page_png = (run_dir / "page.png").read_bytes()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    st.sidebar.caption(f"{manifest['file']} · {manifest['verdict']} · {manifest['mode']}")
    if manifest.get("prompts"):
        st.sidebar.caption("prompt sha: " + ", ".join(f"{k}={v}" for k, v in manifest["prompts"].items()))
    key = run_dir.name
else:
    up = st.sidebar.file_uploader("แบบ (PDF, ไม่บังคับ)", type=["pdf"])
    ai = QuoteSpec()
    if up is not None:
        page_png = render_png(up.getvalue())
    key = f"manual-{up.name if up else 'blank'}"

started = st.session_state.setdefault(f"{key}:started", time.time())

# ---------------------------------------------------------------- layout
left, right = st.columns([3, 2])
with left:
    if page_png:
        st.image(page_png, width="stretch")
    else:
        st.caption("ไม่มีภาพแบบ")

human: dict = {}
human_ev: dict[str, Evidence] = {}


def field(label: str, name: str, widget, **kw):
    """Draw one field with its evidence; a changed or ticked value becomes source=human."""
    ai_val = getattr(ai, name)
    ev = ai.evidence.get(name)
    c1, c2 = st.columns([4, 1])
    with c1:
        val = widget(label, key=f"{key}:{name}", **kw)
        if isinstance(val, str):
            val = val.strip() or None
    with c2:
        st.write("")
        ok = st.checkbox("ยืนยัน", key=f"{key}:{name}:ok", value=bool(ev and ev.source == "human"))
    st.caption(ev_caption(ev))
    human[name] = val
    if ok or val != ai_val:
        human_ev[name] = Evidence(source="human", raw_text=None if val is None else str(val),
                                  note=None if val == ai_val else f"AI: {ai_val!r}")
    elif ev:
        human_ev[name] = ev


def opt_index(options, value):
    return options.index(value) if value in options else 0


with right:
    st.subheader(ai.dwg or "ชิ้นงานใหม่")
    field("Dwg No.", "dwg", st.text_input, value=ai.dwg or "")
    field("ชื่อชิ้น", "name", st.text_input, value=ai.name or "")
    tpl = ["Pioneer", "Summit", "อื่น ๆ", None]
    field("Template ลูกค้า", "template", st.selectbox, options=tpl, index=opt_index(tpl, ai.template),
          format_func=lambda v: v or "ไม่ทราบ")
    mats = [None] + MATERIALS
    field(f"วัสดุ (บนแบบ: {ai.material_raw or '-'})", "material", st.selectbox, options=mats,
          index=opt_index(mats, ai.material), format_func=lambda v: v or "— เลือก —")
    for n, lbl in (("t", "ความหนา t (มม.)"), ("L", "ยาว L (มม.)"), ("W", "กว้าง W (มม.)")):
        field(lbl, n, st.number_input, value=getattr(ai, n), min_value=0.0, step=1.0)
    field("จำนวนชิ้น (Q'ty)", "qty", st.number_input, value=ai.qty, min_value=1, step=1)
    field("จำนวน setup", "setups", st.number_input, value=ai.setups, min_value=1, step=1)
    for n, opts, lbl in (("shape", ["rect", "notched", "complex"], "รูปร่าง"),
                         ("tolerance", ["general", "pm05", "h7", "pm01"], "พิกัดความเผื่อ"),
                         ("finish", [None, "none", "anodize", "black_oxide", "zinc_plate"], "ผิวสำเร็จ")):
        field(lbl, n, st.selectbox, options=opts, index=opt_index(opts, getattr(ai, n)),
              format_func=lambda v: v or "ไม่ระบุ")
    field("งานกลึง", "lathe", st.checkbox, value=ai.lathe)
    field("แบบเป็นภาพสแกน", "from_scan", st.checkbox, value=ai.from_scan)

    st.markdown("**จำนวนงาน (ops)**")
    st.caption(ev_caption(ai.evidence.get("ops")))
    ops_vals = {}
    cols = st.columns(4)
    for i, k in enumerate(OP_KEYS + ["slot_mm", "pocket_cm3"]):
        with cols[i % 4]:
            cur = getattr(ai.ops, k)
            ops_vals[k] = st.number_input(k, value=cur, min_value=type(cur)(0), key=f"{key}:ops:{k}")
    ops_ok = st.checkbox("ยืนยันจำนวนงานทั้งหมด", key=f"{key}:ops:ok")
    hole_circ = st.number_input("hole_circumference_mm", value=float(ai.hole_circumference_mm),
                                min_value=0.0, key=f"{key}:hc")
    notes = st.text_area("หมายเหตุ (1 บรรทัด = 1 ข้อ — แสดงเป็นคำเตือนในใบเสนอราคา)",
                         value="\n".join(ai.notes), key=f"{key}:notes")

    leftovers, conflicts = [], []
    if ai.leftovers:
        st.markdown("**feature ที่ยังไม่ได้คิดราคา**")
        for i, lo in enumerate(ai.leftovers):
            st.json(lo, expanded=False)
            if not st.checkbox("ตัดสินแล้ว (ใส่ใน ops หรือไม่ต้องคิด)", key=f"{key}:lo:{i}"):
                leftovers.append(lo)
    if ai.conflicts:
        st.markdown("**ข้อมูลขัดกัน**")
        for i, c in enumerate(ai.conflicts):
            if not st.checkbox(f"แก้แล้ว: {c}", key=f"{key}:cf:{i}"):
                conflicts.append(c)

# ---------------------------------------------------------------- build + check
ops = Ops(**ops_vals)
if ops_ok or ops != ai.ops:
    human_ev["ops"] = Evidence(source="human", note=None if ops == ai.ops else "แก้จำนวนงาน")
elif "ops" in ai.evidence:
    human_ev["ops"] = ai.evidence["ops"]
spec = QuoteSpec(**human, material_raw=ai.material_raw, ops=ops, hole_circumference_mm=hole_circ,
                 notes=[n.strip() for n in notes.splitlines() if n.strip()],
                 evidence=human_ev, leftovers=leftovers, conflicts=conflicts)
result = check(spec, P)

with left:
    st.subheader("สถานะ")
    for f in result["flags"]:
        {"block": st.error, "warn": st.warning, "info": st.info}[f["level"]](f["msg"])
    risk = result["risk"]
    st.caption(f"ความเสี่ยงที่ควรบวก {risk['total_pct']}% (เพดาน {risk['cap_pct']}%): "
               + (", ".join(f"{k} {p}%" for k, p in risk["items"]) or "ไม่มี"))
    if result["price"]:
        pr = result["price"]
        row = pr["parts"][0]
        st.subheader("ราคา")
        m1, m2, m3 = st.columns(3)
        m1.metric("รวม (บาท)", f"{pr['grand_total']:,}")
        m2.metric("ต่อชิ้น (บาท)", f"{row['each']:,}")
        m3.metric("ช่วงที่ควรเสนอ", f"{pr['band'][0]:,} – {pr['band'][1]:,}")
        st.caption(f"เครื่อง {row['machine_min']:.0f} นาที · มือ {row['hand_min']:.0f} · เตรียม "
                   f"{row['prog_min']:.0f} · ค่าแรง {row['labour']:,} · วัสดุ {row['material_cost']:,} "
                   f"· ผิว {row['finish_cost']:,}")
        with st.expander("ตารางเต็ม"):
            st.code(format_table(pr), language=None)
    else:
        st.info("ยังไม่แสดงราคา จนกว่ารายการสีแดงจะหมด")

    if st.button("ยืนยันและบันทึก", type="primary", disabled=result["price"] is None):
        out = run_dir or RUNS / f"{key}-{datetime.now():%Y%m%d-%H%M%S}"
        out.mkdir(parents=True, exist_ok=True)
        if run_dir is None and page_png:
            (out / "page.png").write_bytes(page_png)
        aid, hum = ai.model_dump(), spec.model_dump()
        skip = {"evidence", "leftovers", "conflicts"}
        corrections = [{"field": k, "ai": aid[k], "human": hum[k]}
                       for k in hum if k not in skip and aid.get(k) != hum[k]]
        (out / "quotespec.human.json").write_text(spec.model_dump_json(indent=1), encoding="utf-8")
        (out / "check.human.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        (out / "corrections.json").write_text(json.dumps(
            {"review_seconds": round(time.time() - started), "saved": datetime.now().isoformat(),
             "corrections": corrections}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        st.success(f"บันทึกแล้วที่ {out} — แก้ไป {len(corrections)} ช่อง")
