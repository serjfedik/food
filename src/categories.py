"""Категории рецептов: загрузка из JSON + рендер плиток на Streamlit."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "categories.json"


@dataclass
class Category:
    key: str
    label: str
    emoji: str
    color: str


@lru_cache(maxsize=1)
def load_categories() -> list[Category]:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return [Category(**c) for c in data.get("default", [])]


def get_category(key: str) -> Category | None:
    if not key:
        return None
    for c in load_categories():
        if c.key == key:
            return c
    return None


def label_of(key: str) -> str:
    c = get_category(key)
    return f"{c.emoji} {c.label}" if c else (key or "—")


def options_for_select() -> list[tuple[str, str]]:
    """[(key, 'emoji label'), ...] для st.selectbox."""
    return [(c.key, f"{c.emoji} {c.label}") for c in load_categories()]


def keys() -> list[str]:
    return [c.key for c in load_categories()]
