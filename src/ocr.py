"""OCR helpers: распознаём текст с изображений и сканов PDF.

Все тяжёлые импорты ленивые, чтобы модуль грузился даже без установленных
Pillow/pytesseract/pdf2image — упадём с понятной ошибкой только при реальном вызове.
"""
from __future__ import annotations

import io


DEFAULT_LANGS = "rus+eng"


class OCRUnavailable(RuntimeError):
    """Поднимается, если pytesseract/tesseract/Pillow/poppler не установлены."""


def _load_pil():
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover
        raise OCRUnavailable(
            "Pillow не установлен. Добавьте Pillow в requirements.txt."
        ) from exc
    return Image, ImageOps


def _load_tesseract():
    try:
        import pytesseract
    except ImportError as exc:  # pragma: no cover
        raise OCRUnavailable(
            "pytesseract не установлен. Добавьте pytesseract в requirements.txt."
        ) from exc
    try:
        pytesseract.get_tesseract_version()
    except Exception as exc:  # pragma: no cover
        raise OCRUnavailable(
            "tesseract не найден в системе. В Streamlit Cloud добавьте 'tesseract-ocr' в packages.txt."
        ) from exc
    return pytesseract


def _load_pdf2image():
    try:
        from pdf2image import convert_from_bytes
    except ImportError as exc:  # pragma: no cover
        raise OCRUnavailable(
            "pdf2image не установлен. Добавьте pdf2image в requirements.txt "
            "и poppler-utils в packages.txt."
        ) from exc
    return convert_from_bytes


def _preprocess(image):
    _, ImageOps = _load_pil()
    gray = ImageOps.grayscale(image)
    return ImageOps.autocontrast(gray, cutoff=2)


def image_to_text(image, langs: str = DEFAULT_LANGS) -> str:
    pytesseract = _load_tesseract()
    prepped = _preprocess(image)
    return pytesseract.image_to_string(prepped, lang=langs)


def image_bytes_to_text(data: bytes, langs: str = DEFAULT_LANGS) -> str:
    Image, _ = _load_pil()
    with Image.open(io.BytesIO(data)) as img:
        return image_to_text(img, langs=langs)


def pdf_bytes_to_text_via_ocr(data: bytes, langs: str = DEFAULT_LANGS, dpi: int = 250) -> str:
    """Растеризуем PDF и распознаём постранично. Для сканов без текстового слоя."""
    convert_from_bytes = _load_pdf2image()
    pages = convert_from_bytes(data, dpi=dpi)
    parts: list[str] = []
    for page in pages:
        parts.append(image_to_text(page, langs=langs))
    return "\n\n".join(parts).strip()
