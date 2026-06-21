"""Vision и AI-OCR через LLM-провайдеров.

Поддерживает 3 провайдера: OpenAI (рекомендуется), Google Gemini (бесплатный
тариф), Anthropic. Автодетект по тому, какой ключ есть в Streamlit secrets.

Возможности:
- `describe_fridge_photo(image_bytes)` — распознать продукты с фото холодильника.
- `ocr_recipe(image_bytes)` — расшифровать рукописный или сложный печатный
  рецепт в чистый markdown-текст (замена Tesseract там, где он не справляется).

Все импорты SDK ленивые: модуль грузится даже без установленных библиотек.

Установка для пользователя (один из трёх вариантов):

  OpenAI:
    1. https://platform.openai.com → API keys → Create
    2. Положить на счёт $5
    3. В Streamlit Secrets:   OPENAI_API_KEY = "sk-..."

  Google Gemini (free tier):
    1. https://aistudio.google.com → Get API Key → Create
    2. В Streamlit Secrets:   GEMINI_API_KEY = "AIza..."

  Anthropic:
    1. https://console.anthropic.com → API Keys → Create
    2. Положить на счёт $5
    3. В Streamlit Secrets:   ANTHROPIC_API_KEY = "sk-ant-..."
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Типы и общие константы
# ---------------------------------------------------------------------------

@dataclass
class ProductGuess:
    name: str
    qty: Optional[float]
    grams: Optional[float]
    confidence: str
    note: str = ""


class VisionUnavailable(RuntimeError):
    """Понятная ошибка для UI: какой провайдер недоступен и что делать."""


PROVIDERS = ("openai", "gemini", "anthropic")  # порядок = приоритет автодетекта

# Дефолтные модели по провайдеру. Для OCR (рукописное) — модели «помощнее»,
# для fridge photo — самые дешёвые.
DEFAULT_MODELS_OCR = {
    "openai":    "gpt-4o",                       # лучшее на рукописном русском
    "gemini":    "gemini-2.0-flash-exp",         # быстрая + бесплатная
    "anthropic": "claude-sonnet-4-6",
}
DEFAULT_MODELS_PRODUCTS = {
    "openai":    "gpt-4o-mini",                  # для счёта продуктов хватает
    "gemini":    "gemini-2.0-flash-exp",
    "anthropic": "claude-haiku-4-5-20251001",
}

AVAILABLE_MODELS_OCR = {
    "openai":    ["gpt-4o", "gpt-4o-mini"],
    "gemini":    ["gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"],
    "anthropic": ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5-20251001"],
}


# ---------------------------------------------------------------------------
# Промпты
# ---------------------------------------------------------------------------

_OCR_PROMPT = """Ты — помощник по распознаванию рукописных и сложных печатных рецептов на русском языке.

ЗАДАЧА: распознать текст с изображения МАКСИМАЛЬНО ТОЧНО и вернуть его как чистый текст.

ПРАВИЛА:
1. Передавай слова буквально. Не «улучшай», не сокращай, не парафразируй.
2. Бледные / нечитаемые места помечай так: [неразборчиво].
3. Если буква/слово прочитано неуверенно — пиши свою версию и добавляй пометку: «[возможно: вариант]».
4. Сохраняй ВСЮ структуру оригинала:
   - заголовки и подзаголовки,
   - нумерованные и маркированные списки,
   - столбики «ингредиент — количество»,
   - годы и пометки на полях.
5. Числа и единицы измерения переноси буквально. Если непонятна единица — поставь [?] после числа.
6. Если на изображении нет читаемого текста — верни ровно одну строку: [текст не распознан].
7. НЕ добавляй комментарии, заголовки типа «Вот распознанный текст:», и НЕ оборачивай в кодоблок.

Верни ТОЛЬКО распознанный текст."""

_FRIDGE_PROMPT = """Ты — кулинарный помощник. На фото — продукты в холодильнике, на столе или на полке.

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
}"""


# ---------------------------------------------------------------------------
# Управление ключами / автодетект провайдера
# ---------------------------------------------------------------------------

_KEY_ENV_NAMES = {
    "openai":    "OPENAI_API_KEY",
    "gemini":    "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def _get_api_key(provider: str) -> Optional[str]:
    env_name = _KEY_ENV_NAMES.get(provider)
    if not env_name:
        return None
    try:
        import streamlit as st
        if env_name in st.secrets:
            return str(st.secrets[env_name])
    except Exception:
        pass
    return os.environ.get(env_name)


def has_api_key(provider: Optional[str] = None) -> bool:
    """provider=None → есть ли вообще хоть один ключ; иначе для конкретного."""
    if provider:
        return bool(_get_api_key(provider))
    return any(_get_api_key(p) for p in PROVIDERS)


def available_providers() -> list[str]:
    return [p for p in PROVIDERS if _get_api_key(p)]


def default_provider() -> Optional[str]:
    return next(iter(available_providers()), None)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def _openai_client():
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise VisionUnavailable(
            "Библиотека openai не установлена. Добавьте `openai>=1.40` в requirements.txt."
        ) from exc
    key = _get_api_key("openai")
    if not key:
        raise VisionUnavailable(
            "OPENAI_API_KEY не задан. Получите ключ на https://platform.openai.com/api-keys "
            "и добавьте в Streamlit Cloud → Settings → Secrets:\n\n"
            'OPENAI_API_KEY = "sk-..."'
        )
    return OpenAI(api_key=key)


def _openai_chat_with_image(prompt: str, image_bytes: bytes, mime_type: str,
                            model: str, max_tokens: int = 4000) -> str:
    client = _openai_client()
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                        },
                    ],
                }
            ],
        )
    except Exception as exc:
        raise VisionUnavailable(f"OpenAI API: {exc}") from exc
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

def _gemini_chat_with_image(prompt: str, image_bytes: bytes, mime_type: str,
                            model: str, max_tokens: int = 4000) -> str:
    try:
        import google.generativeai as genai
    except ImportError as exc:  # pragma: no cover
        raise VisionUnavailable(
            "Библиотека google-generativeai не установлена. "
            "Добавьте `google-generativeai>=0.7` в requirements.txt."
        ) from exc
    key = _get_api_key("gemini")
    if not key:
        raise VisionUnavailable(
            "GEMINI_API_KEY не задан. Получите ключ на https://aistudio.google.com "
            "(бесплатно, без карты) и добавьте в Streamlit Secrets:\n\n"
            'GEMINI_API_KEY = "AIza..."'
        )
    try:
        genai.configure(api_key=key)
        m = genai.GenerativeModel(model)
        response = m.generate_content(
            [prompt, {"mime_type": mime_type, "data": image_bytes}],
            generation_config={"max_output_tokens": max_tokens},
        )
    except Exception as exc:
        raise VisionUnavailable(f"Gemini API: {exc}") from exc
    return response.text or ""


# ---------------------------------------------------------------------------
# Anthropic Claude
# ---------------------------------------------------------------------------

def _anthropic_chat_with_image(prompt: str, image_bytes: bytes, mime_type: str,
                               model: str, max_tokens: int = 4000) -> str:
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover
        raise VisionUnavailable(
            "Библиотека anthropic не установлена. "
            "Добавьте `anthropic>=0.40` в requirements.txt."
        ) from exc
    key = _get_api_key("anthropic")
    if not key:
        raise VisionUnavailable(
            "ANTHROPIC_API_KEY не задан. Получите ключ на https://console.anthropic.com "
            "и добавьте в Streamlit Secrets:\n\n"
            'ANTHROPIC_API_KEY = "sk-ant-..."'
        )
    client = anthropic.Anthropic(api_key=key)
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
                            "source": {"type": "base64", "media_type": mime_type,
                                       "data": b64},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
    except Exception as exc:
        raise VisionUnavailable(f"Anthropic API: {exc}") from exc
    if not response.content:
        return ""
    return "".join(getattr(b, "text", "") for b in response.content)


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------

def _route(provider: Optional[str]) -> str:
    p = provider or default_provider()
    if not p:
        raise VisionUnavailable(
            "Ни один Vision-провайдер не настроен. Добавьте в Streamlit Secrets "
            "один из ключей: OPENAI_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY."
        )
    return p


def _call(prompt: str, image_bytes: bytes, mime_type: str,
          provider: str, model: str, max_tokens: int) -> str:
    if provider == "openai":
        return _openai_chat_with_image(prompt, image_bytes, mime_type, model, max_tokens)
    if provider == "gemini":
        return _gemini_chat_with_image(prompt, image_bytes, mime_type, model, max_tokens)
    if provider == "anthropic":
        return _anthropic_chat_with_image(prompt, image_bytes, mime_type, model, max_tokens)
    raise VisionUnavailable(f"Неизвестный провайдер: {provider}")


def ocr_recipe(image_bytes: bytes, mime_type: str = "image/jpeg",
               provider: Optional[str] = None,
               model: Optional[str] = None,
               max_tokens: int = 4000) -> str:
    """Распознать текст рецепта с изображения. Возвращает чистый markdown-текст."""
    provider = _route(provider)
    model = model or DEFAULT_MODELS_OCR.get(provider) or ""
    text = _call(_OCR_PROMPT, image_bytes, mime_type, provider, model, max_tokens)
    return text.strip()


def ocr_pdf_via_ai(pdf_bytes: bytes,
                   provider: Optional[str] = None,
                   model: Optional[str] = None,
                   dpi: int = 220,
                   max_pages: Optional[int] = None) -> str:
    """Растеризуем PDF постранично и шлём каждую страницу в Vision.

    Возвращает склеенный markdown-текст с разделителями по страницам.
    """
    try:
        from pdf2image import convert_from_bytes
    except ImportError as exc:  # pragma: no cover
        raise VisionUnavailable(
            "pdf2image не установлен. Добавьте `pdf2image` в requirements.txt "
            "и `poppler-utils` в packages.txt."
        ) from exc
    import io
    pages = convert_from_bytes(pdf_bytes, dpi=dpi)
    if max_pages:
        pages = pages[:max_pages]
    out: list[str] = []
    for i, page in enumerate(pages, 1):
        buf = io.BytesIO()
        page.save(buf, format="JPEG", quality=88)
        text = ocr_recipe(buf.getvalue(), mime_type="image/jpeg",
                          provider=provider, model=model)
        out.append(f"### Страница {i}\n\n{text}")
    return "\n\n---\n\n".join(out)


def describe_fridge_photo(image_bytes: bytes, mime_type: str = "image/jpeg",
                          provider: Optional[str] = None,
                          model: Optional[str] = None,
                          max_tokens: int = 2000) -> list[ProductGuess]:
    """Распознать продукты на фото."""
    provider = _route(provider)
    model = model or DEFAULT_MODELS_PRODUCTS.get(provider) or ""
    text = _call(_FRIDGE_PROMPT, image_bytes, mime_type, provider, model, max_tokens)

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
