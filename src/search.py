"""Простой умный поиск по рецептам.

Без LLM: токенизация + подстрочный матч + difflib для опечаток + лёгкая
лемматизация (отсечь окончания) для русского.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any, Iterable


_TOKEN_RE = re.compile(r"[\wёЁ]+", re.UNICODE)
# самые частотные русские окончания (множественные/падежные/прилаг.) — режем при матче
_RU_ENDINGS = ("ами", "ями", "ого", "его", "ому", "ему", "ыми", "ими",
               "ах", "ях", "ой", "ей", "ом", "ем", "ая", "яя", "ое", "ее",
               "ый", "ий", "ую", "юю", "ы", "и", "а", "я", "у", "е", "о", "ь")


def _stem(token: str) -> str:
    token = token.lower()
    for end in _RU_ENDINGS:
        if len(token) > len(end) + 2 and token.endswith(end):
            return token[: -len(end)]
    return token


def _tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN_RE.findall(text or "")]


def _searchable_text(recipe: dict[str, Any]) -> str:
    bits: list[str] = [
        recipe.get("title", ""),
        recipe.get("category", ""),
        recipe.get("notes", ""),
        " ".join(recipe.get("tags") or []),
        " ".join(recipe.get("ingredients") or []),
    ]
    return " ".join(b for b in bits if b)


@dataclass
class Hit:
    score: float
    recipe: dict[str, Any]
    reasons: list[str]


def search(recipes: Iterable[dict[str, Any]], query: str,
           category: str | None = None, only_favorites: bool = False,
           fuzzy_cutoff: float = 0.78) -> list[Hit]:
    """
    Скоринг:
    - совпадение в title          ×3
    - совпадение в category/tags  ×2
    - совпадение в ingredients    ×1.5
    - fuzzy (difflib) в любом     ×1
    Без query — возвращаем по фильтру (category/favorite).
    """
    recipes = list(recipes)
    if category:
        recipes = [r for r in recipes if (r.get("category") or "") == category]
    if only_favorites:
        recipes = [r for r in recipes if r.get("favorite")]

    q_tokens = _tokenize(query) if query else []
    hits: list[Hit] = []

    for r in recipes:
        reasons: list[str] = []
        if not q_tokens:
            hits.append(Hit(score=1.0, recipe=r, reasons=[]))
            continue

        title_toks = _tokenize(r.get("title", ""))
        cat_toks = _tokenize(r.get("category", "") + " " + " ".join(r.get("tags") or []))
        ing_toks = _tokenize(" ".join(r.get("ingredients") or []))
        all_toks = title_toks + cat_toks + ing_toks

        score = 0.0
        for qt in q_tokens:
            matched = False
            for tt in title_toks:
                if qt in tt or tt in qt:
                    score += 3.0
                    reasons.append(f"title:{tt}")
                    matched = True
                    break
            if matched:
                continue
            for ct in cat_toks:
                if qt in ct or ct in qt:
                    score += 2.0
                    reasons.append(f"cat/tag:{ct}")
                    matched = True
                    break
            if matched:
                continue
            for it in ing_toks:
                if qt in it or it in qt:
                    score += 1.5
                    reasons.append(f"ing:{it}")
                    matched = True
                    break
            if matched:
                continue
            # fuzzy fallback
            close = difflib.get_close_matches(qt, all_toks, n=1, cutoff=fuzzy_cutoff)
            if close:
                score += 1.0
                reasons.append(f"~{close[0]}")

        if score > 0:
            hits.append(Hit(score=score, recipe=r, reasons=reasons))

    hits.sort(key=lambda h: (-h.score, h.recipe.get("title", "")))
    return hits
