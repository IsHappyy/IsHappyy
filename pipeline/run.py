"""Run the pipeline on one drawing and save every stage to runs/<name>-<time>/.

    python -m pipeline.run samples/no3.pdf                # vector + vision (needs .env + prompts/)
    python -m pipeline.run samples/no3.pdf --vector-only  # code only, no API call
    python -m pipeline.run samples/no3.pdf --no-cache     # force fresh model calls (stability check)

Then open the result in the checkpoint app:  streamlit run app.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import ROOT, RUNS
from .s1_ingest import ingest, render_png
from .s2_vector import extract
from .s3_assemble import from_partspec, from_vector, merge
from .s4_validate import blocked, risk_premium, validate
from .s6_price import format_table, load_profile, price_parts
from .schemas import QuoteSpec


def check(spec: QuoteSpec, P: dict | None = None) -> dict:
    """validate + risk + price (price only when nothing blocks)."""
    P = P or load_profile()
    flags = validate(spec, P)
    risk = risk_premium(spec, P)
    price = None if blocked(flags) else price_parts([spec.to_part()], P)
    return {"flags": [f.model_dump() for f in flags], "risk": risk, "price": price}


def _git_rev() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def _dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def run(pdf: str | Path, out_root: Path = RUNS, vector_only: bool = False,
        use_cache: bool = True) -> Path:
    pdf = Path(pdf)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = out_root / f"{pdf.stem}-{stamp}"
    out.mkdir(parents=True, exist_ok=False)

    info = ingest(pdf)
    (out / "text_layer.txt").write_text(info.pop("text"), encoding="utf-8")
    _dump(out / "ingest.json", info)
    page_png = render_png(pdf)
    (out / "page.png").write_bytes(page_png)

    spec = QuoteSpec()
    if info["verdict"] in ("VECTOR", "MIXED"):
        vec = extract(pdf)
        _dump(out / "vector.json", vec)
        spec = from_vector(vec)

    vision = None
    if not vector_only:
        from . import llm
        from .s2_vision import RECONCILER, run_readers
        llm.load_dotenv()
        info["text"] = (out / "text_layer.txt").read_text(encoding="utf-8")
        vision = run_readers(page_png, info, use_cache=use_cache)
        info.pop("text")
        _dump(out / "vision.json", vision)
        outs = vision["outputs"]
        rec = outs.get(RECONCILER) or outs.get("feature_reader")
        if isinstance(rec, dict):
            if "title" not in rec and isinstance(outs.get("title_reader"), dict):
                rec = {**rec, "title": outs["title_reader"]}
            spec = merge(spec, from_partspec(rec)) if spec.evidence else from_partspec(rec)

    spec.template = (info.get("template_guess") or {}).get("template")
    spec.from_scan = info["verdict"] == "SCAN"
    _dump(out / "quotespec.ai.json", spec.model_dump())
    result = check(spec)
    _dump(out / "check.ai.json", result)

    _dump(out / "manifest.json", {
        "file": pdf.name,
        "input_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "created": stamp,
        "verdict": info["verdict"],
        "template_guess": info.get("template_guess"),
        "mode": "vector-only" if vector_only else "vector+vision",
        "prompts": {k: m["prompt_sha"] for k, m in (vision or {}).get("meta", {}).items()},
        "models_served": sorted({m["model_served"] for m in (vision or {}).get("meta", {}).values()}),
        "llm_cache": {k: m["cache"] for k, m in (vision or {}).get("meta", {}).items()},
        "skipped_prompts": (vision or {}).get("skipped", []),
        "code_rev": _git_rev(),
    })
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--out", default=str(RUNS))
    ap.add_argument("--vector-only", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args(argv)

    out = run(a.pdf, Path(a.out), vector_only=a.vector_only, use_cache=not a.no_cache)
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    res = json.loads((out / "check.ai.json").read_text(encoding="utf-8"))
    print(f"ผลอยู่ที่ {out}")
    print(f"ไฟล์ {man['file']} · {man['verdict']} · template {man['template_guess']['template']}"
          f" · prompts {man['prompts'] or '-'}")
    if man["skipped_prompts"]:
        print(f"ข้าม prompt ที่ยังไม่มีใน prompts/: {', '.join(man['skipped_prompts'])}")
    for f in res["flags"]:
        print(f"  [{f['level']}] {f['msg']}")
    if res["price"]:
        print(format_table(res["price"]))
        print(f"ความเสี่ยงที่ควรบวก: {res['risk']['total_pct']}%")
    else:
        print("ยังไม่คิดราคา — มีรายการ block ต้องให้คนยืนยันใน `streamlit run app.py`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
