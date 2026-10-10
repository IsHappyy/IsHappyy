"""Measure reading and pricing separately (guide section 12).

    python eval/run_eval.py                         # latest run of every golden case
    python eval/run_eval.py --diff RUN_A RUN_B      # stability: same drawing, two runs
    python eval/run_eval.py --promote RUN_DIR CASE  # human-confirmed run -> eval/golden/CASE/truth.json

Two numbers per case, never blended:
  reading_impact_pct  = price(AI spec) vs price(truth spec)   -> fix readers / rules
  model_error_pct     = price(truth spec) vs quoted_price      -> fix shop_profile / calibration
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import RUNS  # noqa: E402
from pipeline.s6_price import load_profile, price_parts  # noqa: E402
from pipeline.schemas import KEY_FIELDS, OP_KEYS, QuoteSpec  # noqa: E402

GOLDEN = ROOT / "eval" / "golden"
HEADER = ["material", "qty", "t", "L", "W", "tolerance", "finish", "lathe", "setups"]
OPS = OP_KEYS + ["slot_mm", "pocket_cm3"]


def load_spec(path: Path) -> QuoteSpec:
    data = json.loads(path.read_text(encoding="utf-8"))
    return QuoteSpec.model_validate(data.get("quotespec", data))


def same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) <= 0.5
    return a == b


def price_of(spec: QuoteSpec, P) -> float | None:
    if any(getattr(spec, f) is None for f in KEY_FIELDS):
        return None
    return price_parts([spec.to_part()], P)["grand_total"]


def pct(a, b):
    return None if a is None or not b else round((a - b) / b * 100, 1)


def latest_run(file_name: str) -> Path | None:
    hits = []
    for m in RUNS.glob("*/manifest.json"):
        if json.loads(m.read_text(encoding="utf-8")).get("file") == file_name:
            hits.append(m.parent)
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None


def score_case(case: Path, P) -> dict:
    truth_doc = json.loads((case / "truth.json").read_text(encoding="utf-8"))
    truth = QuoteSpec.model_validate(truth_doc["quotespec"])
    run = latest_run(truth_doc["file"])
    row = {"case": case.name, "file": truth_doc["file"], "run": run.name if run else None}
    if not run:
        return {**row, "error": "ยังไม่มีผลรันของไฟล์นี้ใน runs/"}
    ai = load_spec(run / "quotespec.ai.json")

    header_wrong = [f for f in HEADER if not same(getattr(ai, f), getattr(truth, f))]
    ops_wrong = {k: (getattr(ai.ops, k), getattr(truth.ops, k))
                 for k in OPS if not same(getattr(ai.ops, k), getattr(truth.ops, k))}
    p_ai, p_truth = price_of(ai, P), price_of(truth, P)
    quoted = truth_doc.get("quoted_price")
    corr = run / "corrections.json"
    return {**row,
            "header_acc": round(1 - len(header_wrong) / len(HEADER), 3),
            "header_wrong": header_wrong,
            "ops_wrong": ops_wrong,
            "setups_ok": ai.setups == truth.setups,
            "price_ai": p_ai, "price_truth": p_truth, "quoted_price": quoted,
            "reading_impact_pct": pct(p_ai, p_truth),
            "model_error_pct": pct(p_truth, quoted),
            "review_seconds": json.loads(corr.read_text(encoding="utf-8")).get("review_seconds")
            if corr.is_file() else None}


def evaluate() -> int:
    P = load_profile()
    cases = sorted(p for p in GOLDEN.iterdir() if (p / "truth.json").is_file()) if GOLDEN.is_dir() else []
    if not cases:
        print("ยังไม่มีเคสใน eval/golden/ — ดู eval/golden/README.md")
        return 1
    rows = [score_case(c, P) for c in cases]
    print(f"{'case':<18}{'header':>8}{'setup':>7}{'ops ผิด':>9}{'อ่านผิด→ราคา%':>15}{'โมเดล→ราคา%':>13}{'ตรวจ(วิ)':>10}")
    for r in rows:
        if "error" in r:
            print(f"{r['case']:<18}{r['error']}")
            continue
        print(f"{r['case']:<18}{r['header_acc']:>8.0%}{'✓' if r['setups_ok'] else '✗':>7}"
              f"{len(r['ops_wrong']):>9}{str(r['reading_impact_pct']):>15}"
              f"{str(r['model_error_pct']):>13}{str(r['review_seconds']):>10}")
        if r["header_wrong"] or r["ops_wrong"]:
            print(f"{'':<18}ผิด: {r['header_wrong']} {r['ops_wrong']}")
    out = RUNS / "_eval" / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nบันทึกที่ {out}")
    return 0


def diff_runs(a: Path, b: Path) -> int:
    sa, sb = load_spec(a / "quotespec.ai.json"), load_spec(b / "quotespec.ai.json")
    ma = json.loads((a / "manifest.json").read_text(encoding="utf-8"))
    mb = json.loads((b / "manifest.json").read_text(encoding="utf-8"))
    print(f"prompts A={ma.get('prompts')}\nprompts B={mb.get('prompts')}")
    da, db = sa.model_dump(exclude={"evidence"}), sb.model_dump(exclude={"evidence"})
    diffs = [(k, da[k], db[k]) for k in da if da[k] != db[k]]
    for k, x, y in diffs:
        print(f"  {k}: {x!r}  ≠  {y!r}")
    print("เหมือนกันทุกช่อง" if not diffs else f"ต่างกัน {len(diffs)} ช่อง")
    return 0 if not diffs else 2


def promote(run: Path, case: str) -> int:
    src = run / "quotespec.human.json"
    if not src.is_file():
        print(f"ไม่พบ {src} — ยืนยันใน app ก่อน")
        return 1
    man = json.loads((run / "manifest.json").read_text(encoding="utf-8")) \
        if (run / "manifest.json").is_file() else {"file": run.name}
    dst = GOLDEN / case
    dst.mkdir(parents=True, exist_ok=True)
    doc = {"file": man["file"], "quotespec": json.loads(src.read_text(encoding="utf-8")),
           "quoted_price": None, "won": None, "actual_minutes": None}
    (dst / "truth.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"สร้าง {dst / 'truth.json'} แล้ว — เติม quoted_price ถ้าหาราคาเดิมเจอ")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--diff", nargs=2, metavar=("RUN_A", "RUN_B"))
    ap.add_argument("--promote", nargs=2, metavar=("RUN_DIR", "CASE"))
    a = ap.parse_args()
    if a.diff:
        return diff_runs(Path(a.diff[0]), Path(a.diff[1]))
    if a.promote:
        return promote(Path(a.promote[0]), a.promote[1])
    return evaluate()


if __name__ == "__main__":
    sys.exit(main())
