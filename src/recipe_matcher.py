"""Подбор рецептов под имеющиеся в холодильнике продукты.

Без LLM. Алгоритм:
1. Для каждого рецепта парсим строки ингредиентов через `nutrition.calc_ingredient`
   → каноническое имя продукта + нужный вес в граммах.
2. Складываем имеющиеся в холодильнике граммы по каноническому имени.
3. Покрытие = sum(min(есть, нужно)) / sum(нужно) — взвешенно по граммам.
4. Возвращаем рейтинг рецептов с разложением «что есть» / «чего не хватает».
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

from .nutrition import calc_ingredient, load_products


STARTER_PATH = Path(__file__).resolve().parent.parent / "data" / "starter_recipes.json"


@lru_cache(maxsize=1)
def load_starter_recipes() -> list[dict[str, Any]]:
    """Стартовый набор базовых рецептов — используется в матчинге даже до того,
    как пользователь начал заполнять свою библиотеку."""
    try:
        data = json.loads(STARTER_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    recipes = data.get("recipes", [])
    for r in recipes:
        r["_source"] = "starter"
        r["_file_id"] = f"starter:{r.get('title', '')}"
    return recipes


@dataclass
class IngredientStatus:
    line: str               # исходная строка ингредиента
    product_name: str       # каноническое имя из БД (если матчилось)
    needed_g: float         # сколько нужно
    have_g: float           # сколько есть в холодильнике
    short_g: float          # сколько не хватает (>0 если дефицит)
    unmatched: bool = False # True если продукт не найден в БД (≠ нехватка)


@dataclass
class RecipeMatch:
    recipe: dict[str, Any]
    coverage: float                       # 0..1, взвешенно по граммам
    matched_count: int                    # сколько ингредиентов покрыто полностью
    total_with_weights: int               # сколько ингредиентов имеют известный вес
    have: list[IngredientStatus] = field(default_factory=list)
    missing: list[IngredientStatus] = field(default_factory=list)
    unmatched: list[IngredientStatus] = field(default_factory=list)  # «соль по вкусу» и т.п.


def _explode_ingredients(recipe: dict[str, Any]) -> list[IngredientStatus]:
    out: list[IngredientStatus] = []
    for line in (recipe.get("ingredients") or []):
        calc = calc_ingredient(line)
        if not calc.product_name or not calc.grams:
            out.append(IngredientStatus(line=line, product_name=calc.product_name or "",
                                        needed_g=calc.grams or 0.0,
                                        have_g=0.0, short_g=0.0, unmatched=True))
            continue
        out.append(IngredientStatus(line=line, product_name=calc.product_name,
                                    needed_g=calc.grams, have_g=0.0, short_g=0.0))
    return out


def match_recipes(pantry_grams: dict[str, float],
                  recipes: Iterable[dict[str, Any]]) -> list[RecipeMatch]:
    load_products()  # прогреть кэш
    out: list[RecipeMatch] = []
    for r in recipes:
        statuses = _explode_ingredients(r)
        have, missing, unmatched = [], [], []
        total_needed, covered = 0.0, 0.0
        matched_count = 0
        for s in statuses:
            if s.unmatched:
                unmatched.append(s)
                continue
            s.have_g = float(pantry_grams.get(s.product_name, 0.0))
            covered += min(s.have_g, s.needed_g)
            total_needed += s.needed_g
            if s.have_g >= s.needed_g:
                matched_count += 1
            s.short_g = max(0.0, s.needed_g - s.have_g)
            if s.have_g > 0:
                have.append(s)
            if s.short_g > 0:
                missing.append(s)
        coverage = (covered / total_needed) if total_needed else 0.0
        total_with_weights = sum(1 for s in statuses if not s.unmatched)
        out.append(RecipeMatch(
            recipe=r, coverage=coverage, matched_count=matched_count,
            total_with_weights=total_with_weights,
            have=have, missing=missing, unmatched=unmatched,
        ))
    out.sort(key=lambda m: (-m.coverage, -m.matched_count, m.recipe.get("title", "")))
    return out


def suggest(pantry_grams: dict[str, float],
            user_recipes: list[dict[str, Any]],
            include_starter: bool = True,
            top_n: int = 10,
            min_coverage: float = 0.0) -> list[RecipeMatch]:
    """Сортированный список лучших рецептов под холодильник.

    user_recipes: dict-ы из библиотеки пользователя (с `_file_id`).
    include_starter: добавлять ли стартовый набор.
    min_coverage: фильтр по минимальному покрытию (0..1).
    """
    pool: list[dict[str, Any]] = list(user_recipes)
    if include_starter:
        # помечаем, что рецепты пользователя имеют приоритет — добавляем стартовые после
        for r in load_starter_recipes():
            pool.append(r)
    matches = match_recipes(pantry_grams, pool)
    if min_coverage > 0:
        matches = [m for m in matches if m.coverage >= min_coverage]
    return matches[:top_n]
