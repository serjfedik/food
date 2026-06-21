"""Глобальная тема Recipe Vault — на основе сайта masamadre.ru.

Характер: тихий прохладный минимализм. Off-white фон, прохладно-серо-голубые
фотозоны, чёрный текст, всё в нижнем регистре, ТОЛЬКО sans-serif (Inter),
тонкие прямоугольные рамки, отсутствие декора. Акцентом служит не цвет,
а пустое пространство и вес шрифта.

Использование:
    from src.theme import inject_theme, page_header, section_h, hair
    inject_theme()                              # вызвать один раз
    page_header("eyebrow", "title", lead="…")   # шапка страницы
    section_h("01", "название блока")           # подсекция
    hair()                                       # тонкий разделитель
"""
from __future__ import annotations

import streamlit as st


PALETTE = {
    # фоны
    "bg":          "#EFEEEA",   # off-white, чуть тёплый neutral
    "bg_soft":     "#E5E8EA",   # прохладный серо-голубой (для фотозон / sidebar)
    "bg_card":     "#FFFFFF",   # чисто белый
    # текст
    "ink":         "#0E0E0E",   # почти-чёрный
    "ink_dim":     "#3A3A3A",   # вторичный текст
    "ink_mute":    "#8A8A8A",   # caption
    # линии
    "hair":        "#E0E0DC",   # самый тонкий
    "border":      "#CFCFCB",   # видимый бордер
    # акценты (используются ОЧЕНЬ редко — только для функциональных маркеров)
    "accent":      "#0E0E0E",   # сам чёрный и есть акцент
    "photo_bg":    "#E5E8EA",   # «фон под буханку»
    "olive":       "#5A6B45",   # success-маркер (постное, готово)
    "ochre":       "#9C7430",   # warn-маркер (в работе)
}


_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
  --rv-bg:         #EFEEEA;
  --rv-bg-soft:    #E5E8EA;
  --rv-bg-card:    #FFFFFF;
  --rv-ink:        #0E0E0E;
  --rv-ink-dim:    #3A3A3A;
  --rv-ink-mute:   #8A8A8A;
  --rv-hair:       #E0E0DC;
  --rv-border:     #CFCFCB;
  --rv-accent:     #0E0E0E;
  --rv-photo-bg:   #E5E8EA;
  --rv-olive:      #5A6B45;
  --rv-ochre:      #9C7430;

  --rv-radius:     3px;
  --rv-radius-sm:  2px;
  --rv-sans:       'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

/* ============================================================
   База
   ============================================================ */
html, body, [class*="css"], .stApp, .main, .block-container {
  background-color: var(--rv-bg) !important;
  color: var(--rv-ink);
  font-family: var(--rv-sans) !important;
  font-size: 15px;
  -webkit-font-smoothing: antialiased;
}

.block-container {
  padding-top: 2.6rem;
  padding-bottom: 4rem;
  max-width: 1240px;
}

/* Все заголовки — sans, normal-weight, lowercase */
h1, h2, h3, h4, h5,
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
[data-testid="stHeading"] h1,
[data-testid="stHeading"] h2,
[data-testid="stHeading"] h3 {
  font-family: var(--rv-sans) !important;
  color: var(--rv-ink);
  letter-spacing: -0.01em;
  line-height: 1.15;
  font-weight: 600 !important;
  text-transform: lowercase;
}

h1, .stMarkdown h1 { font-size: 2.4rem !important; margin-bottom: .4rem !important; }
h2, .stMarkdown h2 { font-size: 1.7rem !important; margin-top: 1.4rem !important; }
h3, .stMarkdown h3 { font-size: 1.15rem !important; }

.stCaption, [data-testid="stCaptionContainer"], small {
  color: var(--rv-ink-mute) !important;
  font-family: var(--rv-sans) !important;
  font-size: 0.85rem !important;
  font-weight: 400;
}

.stMarkdown p, .stMarkdown li {
  color: var(--rv-ink-dim);
  line-height: 1.6;
}

/* ============================================================
   Sidebar
   ============================================================ */
[data-testid="stSidebar"] {
  background-color: var(--rv-bg) !important;
  border-right: 1px solid var(--rv-hair);
}
[data-testid="stSidebar"] > div:first-child {
  padding-top: 1.5rem;
}
[data-testid="stSidebar"] hr {
  border: none;
  border-top: 1px solid var(--rv-hair);
  margin: 1rem 0;
}

/* ============================================================
   Кнопки — тонкая прямоугольная рамка, никаких pill
   ============================================================ */
.stButton > button, .stDownloadButton > button {
  background: transparent;
  color: var(--rv-ink);
  border: 1px solid var(--rv-border);
  border-radius: var(--rv-radius-sm);
  padding: 0.55rem 1rem;
  font-family: var(--rv-sans);
  font-weight: 400;
  font-size: 0.86rem;
  text-transform: lowercase;
  letter-spacing: 0;
  transition: all .12s ease;
  box-shadow: none !important;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  border-color: var(--rv-ink);
  color: var(--rv-ink);
  background: transparent;
}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background: var(--rv-ink);
  color: #FFFFFF;
  border-color: var(--rv-ink);
  font-weight: 500;
}
.stButton > button[kind="primary"]:hover {
  background: #FFFFFF;
  color: var(--rv-ink);
  border-color: var(--rv-ink);
}

/* Sidebar nav buttons: «кнопки-меню» как у masamadre */
[data-testid="stSidebar"] .stButton > button {
  text-align: left;
  border: 1px solid transparent;
  border-radius: var(--rv-radius-sm);
  padding: 0.45rem 0.7rem;
  font-size: 0.92rem;
  color: var(--rv-ink-dim);
  background: transparent;
}
[data-testid="stSidebar"] .stButton > button:hover {
  color: var(--rv-ink);
  border-color: transparent;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background: transparent;
  color: var(--rv-ink);
  border: 1px solid var(--rv-ink);
  font-weight: 500;
}

/* ============================================================
   Tabs — underline, lowercase
   ============================================================ */
.stTabs [data-baseweb="tab-list"] {
  gap: 1.6rem;
  border-bottom: 1px solid var(--rv-hair);
  margin-bottom: 1.5rem;
}
.stTabs [data-baseweb="tab"] {
  background: transparent !important;
  border: none !important;
  padding: 0.6rem 0 !important;
  font-family: var(--rv-sans);
  font-weight: 400;
  font-size: 0.9rem;
  text-transform: lowercase;
  letter-spacing: 0;
  color: var(--rv-ink-mute) !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
  color: var(--rv-ink) !important;
  border-bottom: 1px solid var(--rv-ink) !important;
  font-weight: 500;
}
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }

/* ============================================================
   Inputs
   ============================================================ */
.stTextInput input, .stTextArea textarea, .stNumberInput input,
.stSelectbox div[data-baseweb="select"] > div,
.stDateInput input, .stMultiSelect div[data-baseweb="select"] > div {
  background: var(--rv-bg-card) !important;
  border: 1px solid var(--rv-border) !important;
  border-radius: var(--rv-radius-sm) !important;
  color: var(--rv-ink) !important;
  font-family: var(--rv-sans) !important;
  font-size: 0.92rem;
  box-shadow: none !important;
}
.stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {
  border-color: var(--rv-ink) !important;
}
[data-testid="stWidgetLabel"] label, .stCheckbox label {
  color: var(--rv-ink-dim) !important;
  font-family: var(--rv-sans) !important;
  font-size: 0.82rem !important;
  font-weight: 400;
  text-transform: lowercase;
}

/* ============================================================
   Метрики — крупные sans-цифры
   ============================================================ */
[data-testid="stMetric"] {
  background: var(--rv-bg-card);
  border: 1px solid var(--rv-border);
  border-radius: var(--rv-radius);
  padding: 14px 18px;
}
[data-testid="stMetricLabel"] {
  color: var(--rv-ink-mute) !important;
  font-size: 0.78rem !important;
  font-weight: 400 !important;
  letter-spacing: 0 !important;
  text-transform: lowercase !important;
}
[data-testid="stMetricValue"] {
  color: var(--rv-ink) !important;
  font-family: var(--rv-sans) !important;
  font-weight: 500 !important;
  font-size: 1.7rem !important;
  letter-spacing: -0.01em;
}

/* ============================================================
   Контейнеры с рамкой (st.container(border=True))
   ============================================================ */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--rv-bg-card) !important;
  border: 1px solid var(--rv-border) !important;
  border-radius: var(--rv-radius) !important;
  padding: 22px 24px !important;
  box-shadow: none !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
  border-color: var(--rv-ink-mute) !important;
}

/* ============================================================
   Expander
   ============================================================ */
[data-testid="stExpander"] {
  background: transparent !important;
  border: 1px solid var(--rv-hair) !important;
  border-radius: var(--rv-radius) !important;
  box-shadow: none !important;
}
[data-testid="stExpander"] summary {
  font-family: var(--rv-sans);
  font-weight: 400;
  color: var(--rv-ink);
  font-size: 0.9rem;
  text-transform: lowercase;
}

/* ============================================================
   Алерты
   ============================================================ */
[data-testid="stAlert"] {
  background: var(--rv-bg-card) !important;
  border: 1px solid var(--rv-border) !important;
  border-left-width: 2px !important;
  border-radius: var(--rv-radius) !important;
  color: var(--rv-ink) !important;
  box-shadow: none !important;
}
[data-testid="stAlert"][data-baseweb="notification"] { padding: 14px 18px !important; }

/* ============================================================
   Dataframe
   ============================================================ */
[data-testid="stDataFrame"] {
  border: 1px solid var(--rv-hair) !important;
  border-radius: var(--rv-radius) !important;
  overflow: hidden;
}

/* ============================================================
   Утилитарные классы
   ============================================================ */
.rv-eyebrow {
  display: inline-block;
  font-family: var(--rv-sans);
  font-size: 0.82rem;
  font-weight: 400;
  letter-spacing: 0;
  color: var(--rv-ink-mute);
  margin-bottom: 0.6rem;
  text-transform: lowercase;
}

/* Mini-rectangle вокруг лейбла — как у masamadre EN/RU, или активного «хлеб» */
.rv-tag {
  display: inline-block;
  border: 1px solid var(--rv-ink);
  border-radius: var(--rv-radius-sm);
  padding: 1px 8px;
  font-size: 0.82rem;
  font-weight: 400;
  color: var(--rv-ink);
}

.rv-display {
  font-family: var(--rv-sans);
  font-weight: 600;
  font-size: 2.6rem;
  line-height: 1.1;
  letter-spacing: -0.015em;
  color: var(--rv-ink);
  margin: 0 0 0.6rem 0;
  text-transform: lowercase;
}

.rv-h {
  font-family: var(--rv-sans);
  font-weight: 600;
  font-size: 1.4rem;
  letter-spacing: -0.005em;
  color: var(--rv-ink);
  margin: 1.4rem 0 0.8rem 0;
  text-transform: lowercase;
}
.rv-h-eyebrow {
  font-family: var(--rv-sans);
  font-size: 0.78rem;
  font-weight: 400;
  letter-spacing: 0;
  color: var(--rv-ink-mute);
  margin-bottom: 0.3rem;
  text-transform: lowercase;
}
.rv-lead {
  font-family: var(--rv-sans);
  font-weight: 400;
  font-size: 1.02rem;
  line-height: 1.55;
  color: var(--rv-ink-dim);
  max-width: 60ch;
}

.rv-caption {
  color: var(--rv-ink-mute);
  font-family: var(--rv-sans);
  font-size: 0.85rem;
}

/* «Карточка хлеба» — белая, минимальный бордер */
.rv-card {
  background: var(--rv-bg-card);
  border: 1px solid var(--rv-border);
  border-radius: var(--rv-radius);
  padding: 22px 24px;
}

/* Плитка с фото-зоной (там, где у masamadre серо-голубой фон под буханкой) */
.rv-tile {
  background: var(--rv-bg-card);
  border: 1px solid var(--rv-border);
  border-radius: var(--rv-radius);
  padding: 20px 20px 18px 20px;
  transition: border-color .12s ease;
  min-height: 150px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.rv-tile:hover {
  border-color: var(--rv-ink);
}
.rv-tile-eyebrow {
  font-family: var(--rv-sans);
  font-size: 0.78rem;
  letter-spacing: 0;
  color: var(--rv-ink-mute);
  text-transform: lowercase;
}
.rv-tile-title {
  font-family: var(--rv-sans);
  font-size: 1.15rem;
  font-weight: 600;
  color: var(--rv-ink);
  margin-top: 0.5rem;
  line-height: 1.2;
  text-transform: lowercase;
}
.rv-tile-meta {
  color: var(--rv-ink-mute);
  font-size: 0.84rem;
  margin-top: 0.4rem;
}

/* Чип-таги */
.rv-pill {
  display: inline-block;
  padding: 1px 8px;
  border: 1px solid var(--rv-border);
  border-radius: var(--rv-radius-sm);
  font-size: 0.74rem;
  color: var(--rv-ink-dim);
  background: transparent;
  margin-right: 4px;
  margin-bottom: 4px;
  text-transform: lowercase;
}
.rv-pill.accent { color: var(--rv-ink); border-color: var(--rv-ink); }
.rv-pill.olive  { color: var(--rv-olive);  border-color: var(--rv-olive); }
.rv-pill.ochre  { color: var(--rv-ochre);  border-color: var(--rv-ochre); }

/* Разделители */
.rv-hair {
  border-top: 1px solid var(--rv-hair);
  margin: 22px 0 16px 0;
}

/* «Фотозона» — для плиток-категорий с прохладно-серо-голубым фоном */
.rv-photo-zone {
  background: var(--rv-photo-bg);
  border-radius: var(--rv-radius);
  aspect-ratio: 4 / 3;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2.2rem;
  color: var(--rv-ink-dim);
  margin-bottom: 12px;
}
</style>
"""


def inject_theme() -> None:
    """Вкручиваем единый CSS-блок. Должно вызываться один раз в начале страницы."""
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(eyebrow: str, title: str, lead: str | None = None) -> None:
    """Шапка страницы: eyebrow (lowercase, mute) → крупный sans-display → lead → hair.

    title и eyebrow выводятся в нижнем регистре — как на masamadre.ru.
    """
    parts = [
        f'<div class="rv-eyebrow">{eyebrow.lower()}</div>',
        f'<div class="rv-display">{title.lower()}</div>',
    ]
    if lead:
        parts.append(f'<div class="rv-lead">{lead}</div>')
    parts.append('<div class="rv-hair"></div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


def section_h(number: str, title: str) -> None:
    """Подсекция: маленький номер/индекс + крупный sans-заголовок."""
    st.markdown(
        f'<div class="rv-h-eyebrow">{number} · {title.lower()}</div>'
        f'<div class="rv-h">{title.lower()}</div>',
        unsafe_allow_html=True,
    )


def hair() -> None:
    st.markdown('<div class="rv-hair"></div>', unsafe_allow_html=True)


def ornament(glyph: str = "") -> None:
    """Совместимости ради — раньше использовался декоративный разделитель.
    В новой теме сводится к обычному hair (без декора, как и просили
    дизайн-референс)."""
    hair()
