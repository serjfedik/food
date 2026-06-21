"""Глобальная тема Recipe Vault — премиальный артизанальный минимализм.

Палитра и типографика вдохновлены проектом Masa Madre: кремовый фон,
тёмная охра вместо чёрного, тонкий terracotta-акцент, hairline-разделители,
крупная serif-типографика для заголовков, sans-serif для тела.

Использование:
    from src.theme import inject_theme
    inject_theme()  # вызвать один раз в начале app.py

После этого можно использовать классы:
    .rv-eyebrow    — мелкий uppercase-лейбл над заголовком
    .rv-display    — крупный serif-заголовок страницы
    .rv-h          — подсекционный serif-заголовок (h2-уровень)
    .rv-caption    — приглушённая подпись
    .rv-card       — белая карточка с hairline-бордером
    .rv-tile       — плитка категории/preset
    .rv-hair       — div-разделитель в одну линию
    .rv-pill       — мелкий тег-чип
"""
from __future__ import annotations

import streamlit as st


PALETTE = {
    # фоны
    "bg":          "#F7F1E5",   # тёплый кремовый, ближе к мякиша
    "bg_soft":     "#EDE5D2",   # пшеничный sidebar
    "bg_card":     "#FFFCF7",   # «бумага» — тёплый белый
    # текст
    "ink":         "#1F1A14",   # тёплый «почти чёрный»
    "ink_dim":     "#6B5E4F",   # вторичный текст
    "ink_mute":    "#9A8E7D",   # caption-уровень
    # линии
    "hair":        "#E3D9C2",   # самый тонкий разделитель
    "border":      "#D8CDB3",   # бордер карточек
    # акценты
    "accent":      "#8E5A3A",   # «корочка хлеба» — древесно-коричневый
    "accent_soft": "#E3CBB5",   # hover/выделение
    "wheat":       "#C9A86A",   # пшеница — для highlight
    "olive":       "#6B7A4A",   # оливка — success / постное
    "ochre":       "#B57F2E",   # warn/в работе
}


_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&family=Inter:wght@300;400;500;600;700&display=swap');

:root {
  --rv-bg:           #F7F1E5;
  --rv-bg-soft:      #EDE5D2;
  --rv-bg-card:      #FFFCF7;
  --rv-ink:          #1F1A14;
  --rv-ink-dim:      #6B5E4F;
  --rv-ink-mute:     #9A8E7D;
  --rv-hair:         #E3D9C2;
  --rv-border:       #D8CDB3;
  --rv-accent:       #8E5A3A;
  --rv-accent-soft:  #E3CBB5;
  --rv-wheat:        #C9A86A;
  --rv-olive:        #6B7A4A;
  --rv-ochre:        #B57F2E;

  --rv-radius:       18px;
  --rv-radius-sm:    10px;
  --rv-serif:        'Cormorant Garamond', 'EB Garamond', Georgia, 'Times New Roman', serif;
  --rv-sans:         'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

/* ============================================================
   Базовая типографика
   ============================================================ */
html, body, [class*="css"], .stApp, .main, .block-container {
  background-color: var(--rv-bg) !important;
  color: var(--rv-ink);
  font-family: var(--rv-sans) !important;
  font-size: 15px;
}

.block-container {
  padding-top: 2.5rem;
  padding-bottom: 4rem;
  max-width: 1180px;
}

/* Заголовки страниц Streamlit -> serif */
h1, h2, h3, h4, h5,
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
[data-testid="stHeading"] h1,
[data-testid="stHeading"] h2,
[data-testid="stHeading"] h3 {
  font-family: var(--rv-serif) !important;
  font-weight: 500 !important;
  letter-spacing: -0.005em;
  color: var(--rv-ink);
  line-height: 1.15;
}

h1, .stMarkdown h1 { font-size: 3.0rem !important; font-weight: 500 !important; margin-bottom: .35rem !important; letter-spacing: -0.015em; }
h2, .stMarkdown h2 { font-size: 2.0rem !important; margin-top: 1.2rem !important; font-weight: 500 !important; letter-spacing: -0.01em; }
h3, .stMarkdown h3 { font-size: 1.45rem !important; font-weight: 500 !important; }

/* Caption / подписи */
.stCaption, [data-testid="stCaptionContainer"], small {
  color: var(--rv-ink-mute) !important;
  font-style: italic;
  font-family: var(--rv-serif) !important;
  font-size: 0.95rem !important;
}

/* Параграфы и списки */
.stMarkdown p, .stMarkdown li {
  color: var(--rv-ink-dim);
  line-height: 1.65;
}

/* ============================================================
   Сайдбар
   ============================================================ */
[data-testid="stSidebar"] {
  background-color: var(--rv-bg-soft) !important;
  border-right: 1px solid var(--rv-hair);
}
[data-testid="stSidebar"] > div:first-child {
  padding-top: 1.5rem;
}
[data-testid="stSidebar"] hr {
  border: none;
  border-top: 1px solid var(--rv-hair);
  margin: 0.9rem 0;
}

/* ============================================================
   Кнопки
   ============================================================ */
.stButton > button, .stDownloadButton > button {
  background: transparent;
  color: var(--rv-ink);
  border: 1px solid var(--rv-border);
  border-radius: 999px;
  padding: 0.55rem 1.2rem;
  font-family: var(--rv-sans);
  font-weight: 500;
  font-size: 0.88rem;
  letter-spacing: 0.02em;
  transition: all .15s ease;
  box-shadow: none !important;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  background: var(--rv-bg-soft);
  border-color: var(--rv-ink-dim);
  color: var(--rv-ink);
}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background: var(--rv-ink);
  color: var(--rv-bg);
  border-color: var(--rv-ink);
}
.stButton > button[kind="primary"]:hover {
  background: var(--rv-accent);
  border-color: var(--rv-accent);
  color: white;
}

/* ============================================================
   Вкладки (st.tabs)
   ============================================================ */
.stTabs [data-baseweb="tab-list"] {
  gap: 1.5rem;
  border-bottom: 1px solid var(--rv-hair);
  margin-bottom: 1.5rem;
}
.stTabs [data-baseweb="tab"] {
  background: transparent !important;
  border: none !important;
  padding: 0.6rem 0 !important;
  font-family: var(--rv-sans);
  font-weight: 500;
  font-size: 0.88rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--rv-ink-mute) !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
  color: var(--rv-ink) !important;
  border-bottom: 1px solid var(--rv-ink) !important;
}
.stTabs [data-baseweb="tab-highlight"] { display: none !important; }

/* ============================================================
   Inputs, selectbox, текстовые поля
   ============================================================ */
.stTextInput input, .stTextArea textarea, .stNumberInput input,
.stSelectbox div[data-baseweb="select"] > div,
.stDateInput input, .stMultiSelect div[data-baseweb="select"] > div {
  background: var(--rv-bg-card) !important;
  border: 1px solid var(--rv-border) !important;
  border-radius: var(--rv-radius-sm) !important;
  color: var(--rv-ink) !important;
  font-family: var(--rv-sans) !important;
  box-shadow: none !important;
}
.stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {
  border-color: var(--rv-ink-dim) !important;
}
[data-testid="stWidgetLabel"] label, .stCheckbox label {
  color: var(--rv-ink-dim) !important;
  font-family: var(--rv-sans) !important;
  font-size: 0.83rem !important;
  font-weight: 500;
  letter-spacing: 0.02em;
}

/* ============================================================
   Метрики st.metric — лаконичный «магазинный ценник»
   ============================================================ */
[data-testid="stMetric"] {
  background: var(--rv-bg-card);
  border: 1px solid var(--rv-border);
  border-radius: var(--rv-radius-sm);
  padding: 14px 18px;
}
[data-testid="stMetricLabel"] {
  color: var(--rv-ink-mute) !important;
  font-size: 0.72rem !important;
  font-weight: 600 !important;
  letter-spacing: 0.14em !important;
  text-transform: uppercase !important;
}
[data-testid="stMetricValue"] {
  color: var(--rv-ink) !important;
  font-family: var(--rv-serif) !important;
  font-weight: 500 !important;
  font-size: 1.85rem !important;
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
  border-radius: var(--rv-radius-sm) !important;
  box-shadow: none !important;
}
[data-testid="stExpander"] summary {
  font-family: var(--rv-sans);
  font-weight: 500;
  color: var(--rv-ink);
  font-size: 0.9rem;
}

/* ============================================================
   Алерты (info / success / warning)
   ============================================================ */
[data-testid="stAlert"] {
  background: var(--rv-bg-card) !important;
  border: 1px solid var(--rv-border) !important;
  border-left-width: 3px !important;
  border-radius: var(--rv-radius-sm) !important;
  color: var(--rv-ink) !important;
  box-shadow: none !important;
}
[data-testid="stAlert"][data-baseweb="notification"] { padding: 14px 18px !important; }

/* ============================================================
   Dataframe
   ============================================================ */
[data-testid="stDataFrame"] {
  border: 1px solid var(--rv-hair) !important;
  border-radius: var(--rv-radius-sm) !important;
  overflow: hidden;
}

/* ============================================================
   Утилитарные классы
   ============================================================ */
.rv-eyebrow {
  display: inline-block;
  font-family: var(--rv-sans);
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--rv-accent);
  margin-bottom: 0.4rem;
}
.rv-display {
  font-family: var(--rv-serif);
  font-weight: 500;
  font-size: 3.6rem;
  line-height: 1.02;
  letter-spacing: -0.015em;
  color: var(--rv-ink);
  margin: 0 0 0.6rem 0;
}
.rv-display em { font-style: italic; color: var(--rv-accent); font-weight: 500; }
.rv-ornament {
  display:flex; align-items:center; gap:14px;
  color: var(--rv-accent); margin: 22px 0 14px 0;
  font-family: var(--rv-serif); font-size: 0.95rem;
}
.rv-ornament::before,
.rv-ornament::after {
  content:""; flex:1; border-top:1px solid var(--rv-hair);
}
.rv-h {
  font-family: var(--rv-serif);
  font-weight: 500;
  font-size: 1.5rem;
  letter-spacing: -0.005em;
  color: var(--rv-ink);
  margin: 1.4rem 0 0.8rem 0;
}
.rv-h-eyebrow {
  font-family: var(--rv-sans);
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--rv-ink-mute);
  margin-bottom: 0.35rem;
}
.rv-lead {
  font-family: var(--rv-serif);
  font-style: italic;
  font-size: 1.15rem;
  line-height: 1.55;
  color: var(--rv-ink-dim);
  max-width: 56ch;
}
.rv-caption {
  color: var(--rv-ink-mute);
  font-family: var(--rv-serif);
  font-style: italic;
  font-size: 0.95rem;
}
.rv-card {
  background: var(--rv-bg-card);
  border: 1px solid var(--rv-border);
  border-radius: var(--rv-radius);
  padding: 24px 26px;
}
.rv-tile {
  background: var(--rv-bg-card);
  border: 1px solid var(--rv-border);
  border-radius: var(--rv-radius);
  padding: 22px 22px 20px 22px;
  transition: border-color .15s ease, transform .15s ease;
  min-height: 150px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.rv-tile:hover {
  border-color: var(--rv-ink-dim);
}
.rv-tile-eyebrow {
  font-family: var(--rv-sans);
  font-size: 0.7rem;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--rv-ink-mute);
}
.rv-tile-title {
  font-family: var(--rv-serif);
  font-size: 1.55rem;
  font-weight: 500;
  color: var(--rv-ink);
  margin-top: 0.4rem;
  line-height: 1.15;
}
.rv-tile-meta {
  color: var(--rv-ink-mute);
  font-size: 0.85rem;
  margin-top: 0.4rem;
}
.rv-pill {
  display: inline-block;
  padding: 2px 10px;
  border: 1px solid var(--rv-border);
  border-radius: 999px;
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  color: var(--rv-ink-dim);
  background: var(--rv-bg-soft);
  margin-right: 4px;
  margin-bottom: 4px;
}
.rv-pill.accent { color: var(--rv-accent); border-color: var(--rv-accent-soft); background: rgba(176,97,61,0.06); }
.rv-pill.olive  { color: var(--rv-olive);  border-color: var(--rv-olive); background: rgba(107,122,74,0.06); }
.rv-pill.ochre  { color: var(--rv-ochre);  border-color: var(--rv-ochre); background: rgba(196,145,68,0.06); }
.rv-hair {
  border-top: 1px solid var(--rv-hair);
  margin: 24px 0 18px 0;
}
.rv-rule-vert {
  border-left: 1px solid var(--rv-hair);
  padding-left: 16px;
}
.rv-section-num {
  font-family: var(--rv-serif);
  font-size: 0.9rem;
  color: var(--rv-accent);
  letter-spacing: 0.15em;
}
</style>
"""


def inject_theme() -> None:
    """Вкручиваем единый CSS-блок. Должно вызываться один раз в начале страницы."""
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(eyebrow: str, title: str, lead: str | None = None) -> None:
    """Премиальный заголовок страницы: eyebrow + serif display + опциональный лид."""
    parts = [f'<div class="rv-eyebrow">{eyebrow}</div>',
             f'<div class="rv-display">{title}</div>']
    if lead:
        parts.append(f'<div class="rv-lead">{lead}</div>')
    parts.append('<div class="rv-hair"></div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


def section_h(eyebrow: str, title: str) -> None:
    """Подсекционный заголовок: small uppercase + serif h2."""
    st.markdown(
        f'<div class="rv-h-eyebrow">{eyebrow}</div>'
        f'<div class="rv-h">{title}</div>',
        unsafe_allow_html=True,
    )


def hair() -> None:
    st.markdown('<div class="rv-hair"></div>', unsafe_allow_html=True)


def ornament(glyph: str = "※") -> None:
    """Хайрлайн с центральным глифом — тонкий «древесный» разделитель.
    Используется ОЧЕНЬ редко, только между смысловыми блоками."""
    st.markdown(f'<div class="rv-ornament">{glyph}</div>',
                unsafe_allow_html=True)
