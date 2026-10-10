"""QuoteSpec: the one contract between reading and pricing.

It is the parts.json schema of the tpt-machining-quote skill plus an `evidence`
entry per field, so every number that reaches the price can be traced back to
where it came from (text layer, vision, a rule, or a human).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Material = Literal["AL", "SUS", "STEEL_MILD", "STEEL_TOOL", "BRASS", "PLASTIC"]
Shape = Literal["rect", "notched", "complex"]
Tolerance = Literal["general", "pm05", "h7", "pm01"]
Finish = Literal["anodize", "black_oxide", "zinc_plate", "none"]
Source = Literal["text_layer", "vision", "rule", "human", "default"]
Confidence = Literal["high", "medium", "low"]
Level = Literal["block", "warn", "info"]

OP_KEYS = ["drill", "drill_deep", "ream", "counterbore", "tap_small", "tap_large",
           "countersink", "bore_circular"]

# fields a human must be able to trust before a price is shown
KEY_FIELDS = ["material", "qty", "t", "L", "W"]


class Evidence(BaseModel):
    source: Source
    raw_text: str | None = None
    confidence: Confidence | None = None
    loc: str | None = None
    note: str | None = None


class Ops(BaseModel):
    drill: int = 0
    drill_deep: int = 0
    ream: int = 0
    counterbore: int = 0
    tap_small: int = 0
    tap_large: int = 0
    countersink: int = 0
    bore_circular: int = 0
    slot_mm: float = 0
    pocket_cm3: float = 0

    def add(self, other: "Ops") -> "Ops":
        return Ops(**{k: getattr(self, k) + getattr(other, k) for k in Ops.model_fields})


class QuoteSpec(BaseModel):
    dwg: str | None = None
    name: str | None = None
    template: str | None = None
    material: Material | None = None
    material_raw: str | None = None
    t: float | None = None
    L: float | None = None
    W: float | None = None
    qty: int | None = None
    setups: int = 1
    shape: Shape = "rect"
    tolerance: Tolerance = "general"
    finish: Finish | None = None
    lathe: bool = False
    from_scan: bool = False
    hole_circumference_mm: float = 0
    ops: Ops = Field(default_factory=Ops)
    notes: list[str] = Field(default_factory=list)

    evidence: dict[str, Evidence] = Field(default_factory=dict)
    leftovers: list[dict] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)

    def to_part(self) -> dict:
        """parts.json entry for s6_price - same shape the skill's estimate.py reads."""
        part = {
            "dwg": self.dwg or "?", "name": self.name or "",
            "material": self.material, "t": self.t, "L": self.L, "W": self.W,
            "qty": self.qty, "setups": self.setups, "shape": self.shape,
            "tolerance": self.tolerance, "finish": self.finish or "none",
            "lathe": self.lathe, "from_scan": self.from_scan,
            "hole_circumference_mm": self.hole_circumference_mm,
            "ops": self.ops.model_dump(), "notes": list(self.notes),
        }
        return {k: v for k, v in part.items() if v is not None}

    def human_confirmed(self, field: str) -> bool:
        ev = self.evidence.get(field)
        return bool(ev and ev.source == "human")


class Flag(BaseModel):
    level: Level
    code: str
    msg: str
    field: str | None = None
