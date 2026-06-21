"""Дневник питания: что и когда ели/планируем съесть.

Хранится единым JSON-файлом в той же папке Google Drive (`meal_log.json`),
читается целиком, изменяется, пишется обратно. Для индивидуального
использования этого достаточно — гонок параллельной записи не ожидается.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any, Iterable


MEAL_TYPES = ("завтрак", "обед", "ужин", "перекус")


@dataclass
class MealEntry:
    id: str
    date: str             # YYYY-MM-DD
    meal_type: str
    recipe_title: str
    recipe_file_id: str   # ссылка на исходный файл Google Doc (если есть)
    portions: float
    nutrition: dict[str, float]    # kcal/protein/fat/carbs
    notes: str = ""
    logged_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MealEntry":
        return cls(
            id=data.get("id") or str(uuid.uuid4()),
            date=data.get("date", ""),
            meal_type=data.get("meal_type", ""),
            recipe_title=data.get("recipe_title", ""),
            recipe_file_id=data.get("recipe_file_id", ""),
            portions=float(data.get("portions") or 1.0),
            nutrition=dict(data.get("nutrition") or {}),
            notes=data.get("notes", ""),
            logged_at=data.get("logged_at", ""),
        )


@dataclass
class MealLog:
    entries: list[MealEntry] = field(default_factory=list)

    def add(self, entry: MealEntry) -> None:
        if not entry.id:
            entry.id = str(uuid.uuid4())
        if not entry.logged_at:
            entry.logged_at = datetime.utcnow().isoformat() + "Z"
        self.entries.append(entry)

    def remove(self, entry_id: str) -> bool:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.id != entry_id]
        return len(self.entries) != before

    def update(self, entry: MealEntry) -> bool:
        for i, e in enumerate(self.entries):
            if e.id == entry.id:
                self.entries[i] = entry
                return True
        return False

    def for_date(self, d: date | str) -> list[MealEntry]:
        key = d.isoformat() if isinstance(d, date) else d
        return [e for e in self.entries if e.date == key]

    def daily_totals(self, d: date | str) -> dict[str, float]:
        totals = {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
        for e in self.for_date(d):
            for k in totals:
                totals[k] += float(e.nutrition.get(k, 0.0))
        return totals

    def range(self, start: date, end: date) -> list[MealEntry]:
        s, e = start.isoformat(), end.isoformat()
        return [x for x in self.entries if s <= x.date <= e]

    def to_dict(self) -> dict[str, Any]:
        return {"version": 1, "entries": [e.to_dict() for e in self.entries]}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "MealLog":
        if not data:
            return cls()
        entries: Iterable[dict[str, Any]] = data.get("entries") or []
        return cls(entries=[MealEntry.from_dict(x) for x in entries])
