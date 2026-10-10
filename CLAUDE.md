# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Drawing-to-quote pipeline for Thai Precision Tool (TPT): read engineering drawings (Pioneer vector PDFs, Summit scans), produce a `QuoteSpec`, have a human confirm it, then price it with a deterministic cost model. The analysis and roadmap behind the design is in `docs/analysis-and-roadmap.md` (Thai).

## Commands

```bash
pip install -r requirements.txt
pytest                                              # all tests; offline, no API key needed
pytest tests/test_price.py::test_parity_with_original_estimate   # single test
python -m pipeline.run samples/X.pdf --vector-only  # code-only run, no API call
python -m pipeline.run samples/X.pdf [--no-cache]   # with vision readers (needs .env + prompts/)
streamlit run app.py                                # human checkpoint UI
python eval/run_eval.py [--diff RUN_A RUN_B | --promote RUN_DIR CASE]
```

## Architecture

Stages in `pipeline/`, each a module, passing one contract: `schemas.QuoteSpec` (the tpt-machining-quote skill's parts.json + an `Evidence` per field saying text_layer / vision / rule / human).

`s1_ingest` (classify, render, template guess from `config/customers.json`) → `s2_vector` (text-layer title block + TAG hole table) and/or `s2_vision` (user's prompts from `prompts/` via `llm.call_json`) → `s3_assemble` (ops counting, `join_by_tag`, `merge`: text layer wins, disagreements become `conflicts`) → `s4_validate` (block/warn/info + risk premium) → human in `app.py` → `s6_price`.

`run.py` writes every stage to `runs/<file>-<time>/` with a `manifest.json` (input sha, prompt shas, model served). `app.py` writes `quotespec.human.json` + `corrections.json`; `eval/run_eval.py` scores AI specs against `eval/golden/<case>/truth.json`, reporting reading error and pricing-model error separately.

## Conventions

- AI only interprets (vision reading, leftovers). Anything expressible as a rule is code. Never replace a vision model call with a script that imitates it; conversely, joins and op counting must stay in code.
- Prompts are read only from `prompts/<name>.md`; their sha is logged per run. Do not hardcode prompt text elsewhere.
- Model ids live in `.env` (`MODEL_READ`, `MODEL_FAST`), never in committed files. Current models reject `temperature`; use `READ_EFFORT`.
- `s6_price.py` must match the skill's `estimate.py` exactly; `tests/fixtures/parity_expected.json` is the original's output. Change the cost model deliberately and regenerate the fixture in the same commit.
- Unknown `feature_type` values go to `QuoteSpec.leftovers` and block pricing; nothing is dropped silently. Map them in `config/feature_map.json`.
- Any key field (material, qty, t, L, W) with low confidence and no human confirmation blocks the price.
- User-facing messages are Thai. Customer drawings stay in `samples/` (gitignored).
