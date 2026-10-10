"""The only place prompts are read from: prompts/<name>.md in this repo.

Every run records each prompt's sha, so "which prompt version produced this
JSON?" always has an answer. Line endings are normalised before hashing so the
same file hashes the same on Windows and Linux.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from . import PROMPTS


@dataclass(frozen=True)
class Prompt:
    name: str
    text: str
    sha: str
    path: Path


def sha12(text: str) -> str:
    norm = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12]


def available(root: Path = PROMPTS) -> list[str]:
    return sorted(p.stem for p in root.glob("*.md") if p.stem.upper() != "README")


def exists(name: str, root: Path = PROMPTS) -> bool:
    return (root / f"{name}.md").is_file()


def load_prompt(name: str, root: Path = PROMPTS) -> Prompt:
    path = root / f"{name}.md"
    if not path.is_file():
        have = ", ".join(available(root)) or "(ว่าง)"
        raise FileNotFoundError(
            f"ไม่พบ prompt '{name}' ที่ {path} — prompt ต้องอยู่ใน prompts/ ของ repo เท่านั้น "
            f"(ตอนนี้มี: {have})")
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return Prompt(name=name, text=text, sha=sha12(text), path=path)
