"""Парсер сырого текста рецепта в структурированный вид.

Эвристика: без LLM. Разбиваем на блоки «название / ингредиенты / шаги»
по типичным маркерам. Любые ошибки правятся вручную в редакторе.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any


INGREDIENT_HEADERS = (
    "ингредиент", "ингредиенты", "состав", "продукты",
    "ingredients", "ingredient",
)
STEPS_HEADERS = (
    "приготовление", "способ приготовления", "шаги", "инструкция", "рецепт", "пошаговый",
    "directions", "method", "instructions", "steps", "preparation",
)
META_PATTERNS = {
    "servings": re.compile(r"(?:порц\w*|servings?)\s*[:\-]?\s*([\d]+(?:\s*-\s*\d+)?)", re.I),
    "time": re.compile(r"(?:время|готов\w*|cook(?:ing)?\s*time|total\s*time)\s*[:\-]?\s*([\w\s\d./-]+?)$", re.I | re.M),
}

BULLET_RE = re.compile(r"^\s*(?:[-*•·▪◦►●]|\d+[.)])\s+")


@dataclass
class Recipe:
    title: str = ""
    servings: str = ""
    time: str = ""
    ingredients: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    notes: str = ""
    raw_text: str = ""
    category: str = ""              # ключ из data/categories.json (например, "soups")
    tags: list[str] = field(default_factory=list)
    favorite: bool = False
    cuisine: str = ""               # кухня (русская, итальянская, …)
    difficulty: str = ""            # easy | medium | hard

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Recipe":
        return cls(
            title=data.get("title", ""),
            servings=data.get("servings", ""),
            time=data.get("time", ""),
            ingredients=list(data.get("ingredients", [])),
            steps=list(data.get("steps", [])),
            notes=data.get("notes", ""),
            raw_text=data.get("raw_text", ""),
            category=data.get("category", ""),
            tags=list(data.get("tags", [])),
            favorite=bool(data.get("favorite", False)),
            cuisine=data.get("cuisine", ""),
            difficulty=data.get("difficulty", ""),
        )

    def to_markdown(self) -> str:
        lines: list[str] = []
        if self.title:
            lines.append(f"# {self.title}")
            lines.append("")
        meta_bits: list[str] = []
        if self.servings:
            meta_bits.append(f"**Порций:** {self.servings}")
        if self.time:
            meta_bits.append(f"**Время:** {self.time}")
        if self.cuisine:
            meta_bits.append(f"**Кухня:** {self.cuisine}")
        if self.difficulty:
            meta_bits.append(f"**Сложность:** {self.difficulty}")
        if meta_bits:
            lines.append(" · ".join(meta_bits))
            lines.append("")
        if self.tags:
            lines.append("Теги: " + ", ".join(f"`{t}`" for t in self.tags))
            lines.append("")
        if self.ingredients:
            lines.append("## Ингредиенты")
            for it in self.ingredients:
                lines.append(f"- {it}")
            lines.append("")
        if self.steps:
            lines.append("## Приготовление")
            for i, st in enumerate(self.steps, 1):
                lines.append(f"{i}. {st}")
            lines.append("")
        if self.notes:
            lines.append("## Заметки")
            lines.append(self.notes)
            lines.append("")
        return "\n".join(lines).strip() + "\n"


def _is_header(line: str, headers: tuple[str, ...]) -> bool:
    clean = line.strip().lower().rstrip(":").strip("#*— -")
    return any(clean.startswith(h) for h in headers)


def _header_tail(line: str) -> str:
    """Текст после двоеточия в строке-заголовке, если есть (`Заметки: текст`)."""
    if ":" not in line:
        return ""
    _, _, tail = line.partition(":")
    return tail.strip()


def _is_meta_line(line: str) -> bool:
    s = line.strip()
    return bool(META_PATTERNS["servings"].search(s) or META_PATTERNS["time"].search(s))


def _strip_bullet(line: str) -> str:
    return BULLET_RE.sub("", line).strip()


def _guess_title(lines: list[str]) -> tuple[str, int]:
    """Берём первую непустую содержательную строку как название."""
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        if _is_header(s, INGREDIENT_HEADERS + STEPS_HEADERS):
            return "", 0
        if len(s) > 120:
            return "", 0
        return s.strip("#*— "), i + 1
    return "", 0


def parse_recipe(text: str) -> Recipe:
    """Грубо разбиваем сырой текст на структуру рецепта."""
    text = (text or "").replace("\r", "")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return Recipe(raw_text=text)

    lines = text.split("\n")
    title, start = _guess_title(lines)

    recipe = Recipe(title=title, raw_text=text)

    # Мета (порции/время) ищем по всему тексту
    m = META_PATTERNS["servings"].search(text)
    if m:
        recipe.servings = m.group(1).strip()
    m = META_PATTERNS["time"].search(text)
    if m:
        recipe.time = m.group(1).strip()

    section = "head"
    buffer_ing: list[str] = []
    buffer_steps: list[str] = []
    buffer_notes: list[str] = []

    for raw_line in lines[start:]:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        if _is_header(stripped, INGREDIENT_HEADERS):
            section = "ingredients"
            tail = _header_tail(stripped)
            if tail:
                buffer_ing.append(_strip_bullet(tail))
            continue
        if _is_header(stripped, STEPS_HEADERS):
            section = "steps"
            tail = _header_tail(stripped)
            if tail:
                buffer_steps.append(_strip_bullet(tail))
            continue
        if _is_header(stripped, ("примечан", "заметк", "совет", "notes", "tip")):
            section = "notes"
            tail = _header_tail(stripped)
            if tail:
                buffer_notes.append(tail)
            continue

        # Метаданные (Порции:/Время:) уже подняли отдельно — не дублируем в секции.
        if _is_meta_line(stripped):
            continue

        if section == "ingredients":
            piece = _strip_bullet(stripped)
            if piece:
                buffer_ing.append(piece)
        elif section == "steps":
            piece = _strip_bullet(stripped)
            if piece:
                buffer_steps.append(piece)
        elif section == "notes":
            buffer_notes.append(stripped)
        else:
            # «head» — до явных заголовков. Если строка похожа на ингредиент
            # (короткая, с числом/единицей) — кладём в ингредиенты, иначе в шаги.
            piece = _strip_bullet(stripped)
            if re.search(r"\d", piece) and len(piece) < 80:
                buffer_ing.append(piece)
            else:
                buffer_steps.append(piece)

    recipe.ingredients = buffer_ing
    recipe.steps = buffer_steps
    recipe.notes = "\n".join(buffer_notes).strip()
    return recipe
