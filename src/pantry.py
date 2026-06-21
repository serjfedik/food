"""Холодильник: список продуктов с весами.

Используется для подбора рецептов по тому, что есть дома. Сохраняется
в Drive как `pantry.json` (по тому же принципу, что и `meal_log.json`).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Iterable, Optional

from .nutrition import (Product, find_product, grams_for, load_products,
                        parse_ingredient)


@dataclass
class PantryItem:
    id: str
    raw: str                 # как ввёл пользователь
    name: str                # очищенное название (из парсера)
    product_name: str        # каноническое название из БД (для матчинга), либо ""
    grams: float             # вес в граммах
    added_at: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PantryItem":
        return cls(
            id=data.get("id") or str(uuid.uuid4()),
            raw=data.get("raw", ""),
            name=data.get("name", ""),
            product_name=data.get("product_name", ""),
            grams=float(data.get("grams") or 0.0),
            added_at=data.get("added_at", ""),
            note=data.get("note", ""),
        )


@dataclass
class Pantry:
    items: list[PantryItem] = field(default_factory=list)

    def add(self, item: PantryItem) -> None:
        if not item.id:
            item.id = str(uuid.uuid4())
        if not item.added_at:
            item.added_at = datetime.utcnow().isoformat() + "Z"
        # Если такой же продукт уже есть — суммируем граммы
        for existing in self.items:
            if existing.product_name and existing.product_name == item.product_name:
                existing.grams += item.grams
                existing.raw = f"{existing.raw} + {item.raw}"
                return
        self.items.append(item)

    def remove(self, item_id: str) -> bool:
        before = len(self.items)
        self.items = [x for x in self.items if x.id != item_id]
        return len(self.items) != before

    def update(self, item: PantryItem) -> bool:
        for i, e in enumerate(self.items):
            if e.id == item.id:
                self.items[i] = item
                return True
        return False

    def clear(self) -> None:
        self.items = []

    def grams_by_product(self) -> dict[str, float]:
        result: dict[str, float] = {}
        for it in self.items:
            if not it.product_name:
                continue
            result[it.product_name] = result.get(it.product_name, 0.0) + it.grams
        return result

    def to_dict(self) -> dict[str, Any]:
        return {"version": 1, "items": [it.to_dict() for it in self.items]}

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "Pantry":
        if not data:
            return cls()
        items: Iterable[dict[str, Any]] = data.get("items") or []
        return cls(items=[PantryItem.from_dict(x) for x in items])


# ---------------------------------------------------------------------------
# Парсер пользовательского ввода
# ---------------------------------------------------------------------------

def parse_user_input(text: str,
                     products: Optional[list[Product]] = None) -> list[PantryItem]:
    """Разбирает многострочный список вида:
        болгарский перец 350 г
        2 огурца
        йогурт 200
    """
    products = products or load_products()
    out: list[PantryItem] = []
    for line in (text or "").splitlines():
        line = line.strip().lstrip("-•·")
        if not line:
            continue
        item = parse_line(line, products=products)
        if item:
            out.append(item)
    return out


def parse_line(line: str,
               products: Optional[list[Product]] = None) -> Optional[PantryItem]:
    products = products or load_products()
    parsed = parse_ingredient(line)
    if not parsed.name and parsed.qty is None:
        return None
    match = find_product(parsed.name, products=products)
    product = match[0] if match else None
    grams = grams_for(parsed, product) or 0.0
    return PantryItem(
        id="",
        raw=line,
        name=parsed.name or line,
        product_name=product.name if product else "",
        grams=float(grams),
    )
