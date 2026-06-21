"""Распознавание продуктов на фото холодильника через Anthropic Claude Vision.

Без LLM в рантайне работают: КБЖУ, поиск, матчинг, OCR-список. Vision —
единственное место в приложении, где без LLM не обойтись (определение объектов
на фото — это не текст и Tesseract тут не поможет).

Установка для пользователя:
1. Зарегистрироваться на https://console.anthropic.com
2. Выпустить API-ключ.
3. В Streamlit Cloud → Settings → Secrets добавить:
       ANTHROPIC_API_KEY = "sk-ant-..."
4. (Опционально) положить ~$5-10 на счёт; одно распознавание ≈ $0.005 на Haiku.

Все импорты anthropic — ленивые: модуль грузится даже без установленной
библиотеки и падает понятной ошибкой только при вызове.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ProductGuess:
    """Один распознанный продукт с оценкой количества."""
    name: str                # «болгарский перец»
    qty: Optional[float]     # 3 (для штучного) или None
    grams: Optional[float]   # оценка веса в граммах
    confidence: str          # 'high' / 'medium' / 'low'
    note: str = ""           # короткий комментарий модели


class VisionUnavailable(RuntimeError):
    """Поднимается, когда не получается распознать (нет ключа, нет библиотеки,
    модель не ответила и т.п.). Сообщение содержит понятную для пользователя
    подсказку, что сделать."""


# Модель по умолчанию — Claude Haiku: быстро и дёшево (~$0.005/фото),
# для распознавания продуктов хватает. Качество выше — у Sonnet/Opus.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


_PROMPT = """Ты — кулинарный помощник. На фото — продукты в холодильнике, на столе или на полке.

ЗАДАЧА: распознать видимые ПРОДУКТЫ ПИТАНИЯ и оценить вес каждого. Никаких выдумок.

ПРАВИЛА:
1. Только то, что реально видно. Если не уверен — ставь confidence "low" или не упоминай.
2. Штучные (яйца, перец, яблоки, помидоры, огурцы) — обязательно указывай qty и grams (суммарный вес группы).
3. Весовые (сметана, молоко, фарш, сыр) — только grams. qty = null.
4. Содержимое упаковки, а не упаковку: «молоко 2.5% 1 л», а не «коробка молока».
5. Названия — на русском, в именительном падеже, единственное число.
6. Жирность указывай, если читается на этикетке (например, «молоко 2.5%», «сметана 20%»).
7. Если на фото есть готовая еда (борщ в кастрюле, пицца) — НЕ включай её как продукт.
8. Если на фото нет продуктов — верни пустой массив.

ФОРМАТ ОТВЕТА — строго валидный JSON, без префиксов, комментариев и markdown:
{
  "products": [
    {"name": "яблоко", "qty": 4, "grams": 720, "confidence": "high", "note": ""},
    {"name": "молоко 2.5%", "qty": null, "grams": 1000, "confidence": "medium", "note": "литровая коробка"},
    {"name": "сметана 20%", "qty": null, "grams": 400, "confidence": "high", "note": ""}
  ]
}
"""


def _load_anthropic():
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise VisionUnavailable(
            "Библиотека anthropic не установлена. "
            "Добавьте `anthropic>=0.40.0` в requirements.txt."
        ) from exc
    return anthropic


def _get_api_key() -> Optional[str]:
    # сначала secrets (Streamlit), потом env (для локального запуска)
    try:
        import streamlit as st
        if "ANTHROPIC_API_KEY" in st.secrets:
            return str(st.secrets["ANTHROPIC_API_KEY"])
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY")


def has_api_key() -> bool:
    return bool(_get_api_key())


def describe_fridge_photo(image_bytes: bytes,
                          mime_type: str = "image/jpeg",
                          model: str = DEFAULT_MODEL,
                          max_tokens: int = 1500) -> list[ProductGuess]:
    """Послать фото в Claude Vision и получить список распознанных продуктов.

    Возвращает пустой список, если на фото нет продуктов. Поднимает
    VisionUnavailable с понятной ошибкой, если нет ключа / нет библиотеки /
    модель не вернула валидный JSON.
    """
    anthropic = _load_anthropic()
    api_key = _get_api_key()
    if not api_key:
        raise VisionUnavailable(
            "ANTHROPIC_API_KEY не задан.\n\n"
            "Добавьте ключ в Streamlit Cloud → Settings → Secrets:\n\n"
            'ANTHROPIC_API_KEY = "sk-ant-..."\n\n'
            "Ключ выпускается на https://console.anthropic.com → API Keys."
        )

    client = anthropic.Anthropic(api_key=api_key)
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": _PROMPT},
                    ],
                }
            ],
        )
    except Exception as exc:
        raise VisionUnavailable(f"Anthropic API: {exc}") from exc

    if not response.content:
        raise VisionUnavailable("Пустой ответ модели.")

    text = "".join(
        getattr(block, "text", "") for block in response.content
    )

    # Достаём JSON из ответа на случай, если модель обернула в текст
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        raise VisionUnavailable(
            f"Модель не вернула JSON. Сырой ответ:\n\n{text[:400]}"
        )
    try:
        data = json.loads(text[start:end])
    except json.JSONDecodeError as exc:
        raise VisionUnavailable(
            f"Не удалось разобрать JSON: {exc}\n\nСырой:\n{text[:400]}"
        ) from exc

    products: list[ProductGuess] = []
    for raw in data.get("products") or []:
        name = (raw.get("name") or "").strip()
        if not name:
            continue
        products.append(ProductGuess(
            name=name,
            qty=_safe_float(raw.get("qty")),
            grams=_safe_float(raw.get("grams")),
            confidence=str(raw.get("confidence") or "medium"),
            note=str(raw.get("note") or "").strip(),
        ))
    return products


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
