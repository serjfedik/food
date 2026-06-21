"""Google Sheets как вторичная база знаний.

Идея: в Drive рецепты лежат как Google Doc + JSON-бэкап (один файл на рецепт).
В Sheets — ровные таблицы для быстрого просмотра, фильтра и экспорта:
- Вкладка «Рецепты»     — одна строка = один рецепт.
- Вкладка «Дневник»     — записи приёмов пищи.
- Вкладка «Холодильник» — текущие продукты с весами.

Используется тот же сервисный аккаунт, что и для Drive. ID мастер-таблицы
передаётся через секреты Streamlit:
    [google_sheets]
    spreadsheet_id = "..."

Все импорты gspread ленивые: модуль грузится даже без библиотеки и падает
понятной ошибкой только при попытке вызвать клиент.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional


# ---------------------------------------------------------------------------
# Заголовки вкладок (порядок колонок)
# ---------------------------------------------------------------------------

RECIPE_HEADERS = [
    "file_id", "название", "категория", "теги", "кухня", "сложность",
    "порций", "время", "избранное", "ингредиенты", "шаги", "заметки",
    "ссылка в drive", "обновлено",
]

DIARY_HEADERS = [
    "id", "дата", "приём пищи", "блюдо", "порций",
    "ккал", "белки", "жиры", "углеводы",
    "заметка", "сохранено",
]

PANTRY_HEADERS = [
    "id", "введено", "название", "продукт в БД", "граммов",
    "добавлено", "заметка",
]


class SheetsError(RuntimeError):
    """Понятная ошибка для UI."""


def _load_gspread():
    try:
        import gspread
        from gspread.exceptions import APIError, WorksheetNotFound
    except ImportError as exc:  # pragma: no cover
        raise SheetsError(
            "Библиотека gspread не установлена. "
            "Добавьте `gspread>=6.0.0` в requirements.txt."
        ) from exc
    return gspread, APIError, WorksheetNotFound


# ---------------------------------------------------------------------------
# Клиент
# ---------------------------------------------------------------------------

class SheetsClient:
    def __init__(self, service_account_info: dict[str, Any], spreadsheet_id: str):
        if not spreadsheet_id:
            raise SheetsError("Не задан spreadsheet_id мастер-таблицы.")
        gspread, _, _ = _load_gspread()
        try:
            self._gc = gspread.service_account_from_dict(service_account_info)
        except Exception as exc:
            raise SheetsError(f"Не удалось создать клиент: {exc}") from exc
        try:
            self._sh = self._gc.open_by_key(spreadsheet_id)
        except Exception as exc:
            raise SheetsError(
                f"Не удалось открыть таблицу `{spreadsheet_id}`: {exc}\n\n"
                "Убедитесь, что таблица расшарена с email сервисного аккаунта "
                "(права Editor)."
            ) from exc
        self.spreadsheet_id = spreadsheet_id

    @property
    def url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}"

    def _ensure_worksheet(self, name: str, headers: list[str]):
        _, _, WorksheetNotFound = _load_gspread()
        try:
            ws = self._sh.worksheet(name)
        except WorksheetNotFound:
            ws = self._sh.add_worksheet(title=name, rows=200, cols=max(20, len(headers)))
            ws.update("A1", [headers], value_input_option="USER_ENTERED")
        else:
            # Если заголовки разъехались — переписываем первую строку
            current = ws.row_values(1)
            if current != headers:
                ws.update("A1", [headers], value_input_option="USER_ENTERED")
        return ws

    # ----- Рецепты ----------------------------------------------------------

    def upsert_recipe(self, recipe_dict: dict[str, Any],
                      file_id: str, drive_link: str = "") -> None:
        """Добавляет или обновляет строку по file_id."""
        ws = self._ensure_worksheet("Рецепты", RECIPE_HEADERS)
        row = _recipe_row(recipe_dict, file_id, drive_link)
        # Ищем существующую строку по file_id (колонка A)
        col_a = ws.col_values(1)[1:]  # пропускаем header
        try:
            idx = col_a.index(file_id)
            row_n = idx + 2  # +1 на header, +1 за 1-based
            ws.update(f"A{row_n}", [row], value_input_option="USER_ENTERED")
        except ValueError:
            ws.append_row(row, value_input_option="USER_ENTERED")

    def replace_diary(self, entries: Iterable[dict[str, Any]]) -> None:
        ws = self._ensure_worksheet("Дневник", DIARY_HEADERS)
        ws.clear()
        rows = [DIARY_HEADERS] + [_diary_row(e) for e in entries]
        ws.update("A1", rows, value_input_option="USER_ENTERED")

    def replace_pantry(self, items: Iterable[dict[str, Any]]) -> None:
        ws = self._ensure_worksheet("Холодильник", PANTRY_HEADERS)
        ws.clear()
        rows = [PANTRY_HEADERS] + [_pantry_row(it) for it in items]
        ws.update("A1", rows, value_input_option="USER_ENTERED")


# ---------------------------------------------------------------------------
# Сериализация строк
# ---------------------------------------------------------------------------

def _recipe_row(r: dict[str, Any], file_id: str, drive_link: str) -> list[str]:
    ingredients = "\n".join(r.get("ingredients") or [])
    steps_lines = [f"{i}. {s}" for i, s in enumerate(r.get("steps") or [], 1)]
    tags = ", ".join(r.get("tags") or [])
    return [
        file_id,
        r.get("title", ""),
        r.get("category", ""),
        tags,
        r.get("cuisine", ""),
        r.get("difficulty", ""),
        str(r.get("servings", "")),
        r.get("time", ""),
        "★" if r.get("favorite") else "",
        ingredients,
        "\n".join(steps_lines),
        r.get("notes", ""),
        drive_link,
        datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
    ]


def _diary_row(e: dict[str, Any]) -> list[str]:
    n = e.get("nutrition") or {}
    return [
        e.get("id", ""),
        e.get("date", ""),
        e.get("meal_type", ""),
        e.get("recipe_title", ""),
        f'{float(e.get("portions") or 0):g}',
        f'{float(n.get("kcal") or 0):.0f}',
        f'{float(n.get("protein") or 0):.1f}',
        f'{float(n.get("fat") or 0):.1f}',
        f'{float(n.get("carbs") or 0):.1f}',
        e.get("notes", ""),
        e.get("logged_at", ""),
    ]


def _pantry_row(it: dict[str, Any]) -> list[str]:
    return [
        it.get("id", ""),
        it.get("raw", ""),
        it.get("name", ""),
        it.get("product_name", ""),
        f'{float(it.get("grams") or 0):.0f}',
        it.get("added_at", ""),
        it.get("note", ""),
    ]
