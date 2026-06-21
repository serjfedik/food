"""Калькулятор КБЖУ.

Парсит строки ингредиентов (свободного формата), приводит к граммам,
матчит на локальную CSV-БД продуктов и считает калории/белки/жиры/углеводы.
"""
from __future__ import annotations

import csv
import difflib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NUTRITION_CSV = DATA_DIR / "nutrition_ru.csv"


# ---- Единицы измерения и веса «по умолчанию» --------------------------------

UNIT_TO_GRAMS: dict[str, float] = {
    "г": 1, "гр": 1, "грамм": 1, "граммa": 1, "граммов": 1, "грамма": 1, "г.": 1, "gr": 1,
    "кг": 1000, "килограмм": 1000, "килограмма": 1000, "килограммов": 1000,
    "мл": 1, "миллилитр": 1, "миллилитра": 1, "миллилитров": 1, "ml": 1,
    "л": 1000, "литр": 1000, "литра": 1000, "литров": 1000,
    "ст.л": 15, "ст.л.": 15, "стл": 15, "столовая ложка": 15, "столовой ложки": 15,
    "столовых ложек": 15, "столовые ложки": 15, "ст. л.": 15, "ст. ложка": 15,
    "ч.л": 5, "ч.л.": 5, "чл": 5, "чайная ложка": 5, "чайной ложки": 5,
    "чайных ложек": 5, "чайные ложки": 5, "ч. л.": 5, "ч. ложка": 5,
    "дес.л": 10, "десертная ложка": 10,
    "стакан": 250, "стакана": 250, "стаканов": 250, "стаканы": 250,
    "щепотка": 1, "щепотки": 1, "щепоток": 1,
    "пучок": 30, "пучка": 30, "пучков": 30,
    "долька": 5, "дольки": 5, "долек": 5,
    "капля": 0.05, "капли": 0.05, "капель": 0.05,
    "банка": 400, "банки": 400, "банок": 400,
    "пачка": 200, "пачки": 200, "пачек": 200,
}

# единицы «штука» — переводятся через `piece_g` продукта или fallback 100 г
PIECE_UNITS = {"шт", "шт.", "штук", "штука", "штуки", "штуку", "штучка"}

# вытаскиваем число вида 1, 1.5, 1,5, 1/2, ½, ¾
NUMBER_PATTERN = re.compile(
    r"(?:\d+(?:[.,]\d+)?(?:\s*/\s*\d+)?|½|¼|¾|⅓|⅔|⅛|⅜|⅝|⅞)"
)
FRACTION_MAP = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3,
                "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875}

IGNORE_PHRASES = ("по вкусу", "для подачи", "для смазывания", "по желанию",
                  "опционально", "немного")

# Самые «болтливые» единицы должны проверяться первыми (длиннее)
_UNITS_SORTED = sorted(set(UNIT_TO_GRAMS.keys()) | PIECE_UNITS, key=len, reverse=True)


def _parse_number(token: str) -> Optional[float]:
    token = token.strip()
    if not token:
        return None
    if token in FRACTION_MAP:
        return FRACTION_MAP[token]
    if "/" in token:
        a, b = (p.strip() for p in token.split("/", 1))
        try:
            return float(a) / float(b) if float(b) else None
        except ValueError:
            return None
    try:
        return float(token.replace(",", "."))
    except ValueError:
        return None


# ---- БД продуктов ----------------------------------------------------------

@dataclass
class Product:
    name: str
    aliases: list[str]
    kcal: float
    protein: float
    fat: float
    carbs: float
    piece_g: Optional[float]  # вес одной «штуки» (если применимо)

    @property
    def all_names(self) -> list[str]:
        return [self.name, *self.aliases]


@lru_cache(maxsize=1)
def load_products(path: Optional[str] = None) -> list[Product]:
    csv_path = Path(path) if path else NUTRITION_CSV
    products: list[Product] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            piece_raw = (row.get("piece_g") or "").strip()
            try:
                piece = float(piece_raw) if piece_raw else None
            except ValueError:
                piece = None
            aliases = [a.strip().lower() for a in (row.get("aliases") or "").split("|") if a.strip()]
            products.append(
                Product(
                    name=row["name"].strip().lower(),
                    aliases=aliases,
                    kcal=float(row["kcal"]),
                    protein=float(row["protein"]),
                    fat=float(row["fat"]),
                    carbs=float(row["carbs"]),
                    piece_g=piece,
                )
            )
    return products


# ---- Парсинг строки ингредиента -------------------------------------------

@dataclass
class ParsedIngredient:
    raw: str
    name: str = ""
    qty: Optional[float] = None
    unit: Optional[str] = None
    grams: Optional[float] = None
    note: str = ""

    def is_quantified(self) -> bool:
        return self.grams is not None and self.grams > 0


def _strip_parens(text: str) -> tuple[str, str]:
    """Возвращает (text без скобок, содержимое скобок) для подсказок типа '(крупный)'."""
    m = re.search(r"\(([^)]*)\)", text)
    if not m:
        return text, ""
    note = m.group(1).strip()
    cleaned = (text[: m.start()] + text[m.end():]).strip(" ,")
    return cleaned, note


def _extract_unit(text: str) -> tuple[Optional[str], str]:
    """Ищем единицу измерения. Возвращаем (unit, остаток без единицы)."""
    lower = " " + text.lower() + " "
    for unit in _UNITS_SORTED:
        u_padded = f" {unit} "
        idx = lower.find(u_padded)
        if idx != -1:
            cleaned = (lower[:idx] + " " + lower[idx + len(u_padded):]).strip()
            return unit, re.sub(r"\s+", " ", cleaned)
    # «г.» с точкой — частный случай в конце токена
    for unit in (".г.", " г ", " кг ", " мл ", " л "):
        idx = lower.find(unit)
        if idx != -1:
            cleaned = (lower[:idx] + " " + lower[idx + len(unit):]).strip()
            return unit.strip(". "), re.sub(r"\s+", " ", cleaned)
    return None, text.lower().strip()


def parse_ingredient(line: str) -> ParsedIngredient:
    raw = line.strip()
    if not raw:
        return ParsedIngredient(raw=line)

    cleaned, note = _strip_parens(raw)
    lower = cleaned.lower()

    # фразы вроде «соль по вкусу» — оставляем без количества
    skip_qty = any(phrase in lower for phrase in IGNORE_PHRASES)

    qty: Optional[float] = None
    if not skip_qty:
        nums = NUMBER_PATTERN.findall(lower)
        if nums:
            qty = _parse_number(nums[0])

    unit, after_unit = _extract_unit(lower)
    name = NUMBER_PATTERN.sub(" ", after_unit)
    name = re.sub(r"[—\-–:•·]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" ,.;")

    return ParsedIngredient(raw=raw, name=name, qty=qty, unit=unit, note=note)


# ---- Матчинг названия в БД -------------------------------------------------

def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def find_product(name: str, products: Optional[list[Product]] = None,
                 cutoff: float = 0.6) -> Optional[tuple[Product, float]]:
    """Подбираем продукт по нечёткому совпадению. Возвращаем (продукт, score 0..1)."""
    if not name:
        return None
    products = products or load_products()
    target = _normalize(name)
    if not target:
        return None

    best: Optional[tuple[Product, float]] = None
    for p in products:
        for candidate in p.all_names:
            cand = _normalize(candidate)
            if not cand:
                continue
            if cand == target:
                return p, 1.0
            if cand in target or target in cand:
                # бонус за подстроку
                score = 0.85 + 0.1 * (min(len(cand), len(target)) / max(len(cand), len(target)))
            else:
                score = difflib.SequenceMatcher(None, target, cand).ratio()
            if best is None or score > best[1]:
                best = (p, score)
    if best and best[1] >= cutoff:
        return best
    return None


# ---- Вычисление КБЖУ -------------------------------------------------------

@dataclass
class Nutrition:
    kcal: float = 0.0
    protein: float = 0.0
    fat: float = 0.0
    carbs: float = 0.0

    def scale(self, factor: float) -> "Nutrition":
        return Nutrition(
            kcal=self.kcal * factor,
            protein=self.protein * factor,
            fat=self.fat * factor,
            carbs=self.carbs * factor,
        )

    def __add__(self, other: "Nutrition") -> "Nutrition":
        return Nutrition(
            kcal=self.kcal + other.kcal,
            protein=self.protein + other.protein,
            fat=self.fat + other.fat,
            carbs=self.carbs + other.carbs,
        )

    def round(self, n: int = 1) -> "Nutrition":
        return Nutrition(
            kcal=round(self.kcal, n),
            protein=round(self.protein, n),
            fat=round(self.fat, n),
            carbs=round(self.carbs, n),
        )

    def to_dict(self) -> dict[str, float]:
        return {"kcal": self.kcal, "protein": self.protein,
                "fat": self.fat, "carbs": self.carbs}


@dataclass
class IngredientNutrition:
    parsed: ParsedIngredient
    grams: Optional[float]
    product_name: Optional[str]
    match_score: float
    nutrition: Nutrition
    warning: str = ""


def grams_for(parsed: ParsedIngredient, product: Optional[Product]) -> Optional[float]:
    """Сколько граммов скрывается за qty+unit. None если непонятно."""
    if parsed.qty is None:
        return None
    unit = (parsed.unit or "").lower().strip()
    if unit in PIECE_UNITS:
        per_piece = (product.piece_g if product else None) or 100.0
        return parsed.qty * per_piece
    if unit in UNIT_TO_GRAMS:
        return parsed.qty * UNIT_TO_GRAMS[unit]
    if unit is None or unit == "":
        # qty без единицы — трактуем как «штуки», если продукт это поддерживает,
        # иначе как граммы (обычная привычка «500 капусты» → 500 г).
        if product and product.piece_g:
            return parsed.qty * product.piece_g
        # эвристика: маленькое целое < 20 — скорее «штуки», иначе — граммы.
        if parsed.qty == int(parsed.qty) and parsed.qty < 20:
            return parsed.qty * 100.0
        return parsed.qty
    return None


def calc_ingredient(line: str,
                    products: Optional[list[Product]] = None) -> IngredientNutrition:
    parsed = parse_ingredient(line)
    if not parsed.name:
        return IngredientNutrition(parsed=parsed, grams=None, product_name=None,
                                   match_score=0.0, nutrition=Nutrition(),
                                   warning="пустая строка")
    match = find_product(parsed.name, products=products)
    product = match[0] if match else None
    score = match[1] if match else 0.0
    grams = grams_for(parsed, product)
    if product is None:
        return IngredientNutrition(parsed=parsed, grams=grams, product_name=None,
                                   match_score=0.0, nutrition=Nutrition(),
                                   warning=f"продукт не найден в БД: «{parsed.name}»")
    if grams is None:
        return IngredientNutrition(parsed=parsed, grams=None,
                                   product_name=product.name,
                                   match_score=score, nutrition=Nutrition(),
                                   warning="не удалось определить вес")
    factor = grams / 100.0
    n = Nutrition(
        kcal=product.kcal * factor,
        protein=product.protein * factor,
        fat=product.fat * factor,
        carbs=product.carbs * factor,
    )
    return IngredientNutrition(parsed=parsed, grams=grams,
                               product_name=product.name,
                               match_score=score, nutrition=n)


@dataclass
class RecipeNutrition:
    items: list[IngredientNutrition] = field(default_factory=list)
    total: Nutrition = field(default_factory=Nutrition)
    total_grams: float = 0.0
    servings: float = 1.0

    @property
    def per_serving(self) -> Nutrition:
        if self.servings <= 0:
            return self.total
        return self.total.scale(1.0 / self.servings)

    @property
    def per_100g(self) -> Nutrition:
        if self.total_grams <= 0:
            return Nutrition()
        return self.total.scale(100.0 / self.total_grams)


def calc_recipe(ingredients: list[str], servings: float = 1.0,
                products: Optional[list[Product]] = None) -> RecipeNutrition:
    products = products or load_products()
    items: list[IngredientNutrition] = []
    total = Nutrition()
    total_g = 0.0
    for line in ingredients:
        item = calc_ingredient(line, products=products)
        items.append(item)
        total = total + item.nutrition
        if item.grams:
            total_g += item.grams
    return RecipeNutrition(
        items=items, total=total, total_grams=total_g,
        servings=max(servings, 0.0001),
    )


def parse_servings(text: str) -> float:
    """Достаёт число из строки порций («6», «4-6 порций», «на 8 человек»)."""
    if not text:
        return 1.0
    m = re.search(r"\d+", text)
    return float(m.group(0)) if m else 1.0
