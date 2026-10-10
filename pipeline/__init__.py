"""Drawing-to-quote pipeline for TPT.

Stage order (see docs/analysis-and-roadmap.md):
  s1_ingest -> s2_vector / s2_vision -> s3_assemble -> s4_validate -> [human: app.py] -> s6_price
Everything passes a QuoteSpec (pipeline/schemas.py) between stages.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
PROMPTS = ROOT / "prompts"
RUNS = ROOT / "runs"
