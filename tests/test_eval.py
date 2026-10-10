import importlib.util
import json
from pathlib import Path

from pipeline.run import run

spec = importlib.util.spec_from_file_location(
    "run_eval", Path(__file__).resolve().parent.parent / "eval" / "run_eval.py")
run_eval = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_eval)


def test_score_case_separates_reading_error_from_model_error(vector_pdf, tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    out = run(vector_pdf, out_root=runs, vector_only=True)
    monkeypatch.setattr(run_eval, "RUNS", runs)

    truth = json.loads((out / "quotespec.ai.json").read_text(encoding="utf-8"))
    truth["L"], truth["W"] = 210, 150          # the human measured a different length
    case = tmp_path / "golden" / "tk2638"
    case.mkdir(parents=True)
    (case / "truth.json").write_text(json.dumps(
        {"file": vector_pdf.name, "quotespec": truth, "quoted_price": 3000}), encoding="utf-8")

    r = run_eval.score_case(case, run_eval.load_profile())
    assert r["header_wrong"] == ["L"]
    assert r["setups_ok"] and r["ops_wrong"] == {}
    assert r["reading_impact_pct"] < 0         # AI's shorter L under-prices
    assert r["model_error_pct"] is not None
