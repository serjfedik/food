"""Рендер раздела «О разработке» (4 вкладки + автор + подробный гайд).

Использует глобальную тему из `src/theme.py` — CSS-переменные --rv-* и
утилитарные классы .rv-*.
"""
from __future__ import annotations

import streamlit as st

from . import about_data as data
from .theme import hair, page_header, section_h


def _tile_goal(emoji: str, title: str, body: str) -> str:
    return (
        '<div class="rv-tile" style="min-height:170px;">'
        f'<div>'
        f'  <div class="rv-tile-eyebrow">{emoji}</div>'
        f'  <div style="font-size:1rem;font-weight:600;color:var(--rv-ink);'
        f'margin:.4rem 0 .5rem 0;line-height:1.25;text-transform:lowercase;">'
        f'{title.lower()}</div>'
        f'</div>'
        f'<div style="color:var(--rv-ink-dim);font-size:.85rem;line-height:1.55;">{body}</div>'
        '</div>'
    )


def _tile_adv(title: str, body: str) -> str:
    return (
        '<div class="rv-tile" style="min-height:140px;">'
        f'<div>'
        f'  <div style="font-size:.98rem;font-weight:600;color:var(--rv-ink);'
        f'margin-bottom:.4rem;line-height:1.25;text-transform:lowercase;">'
        f'{title.lower()}</div>'
        f'  <div style="color:var(--rv-ink-dim);font-size:.85rem;line-height:1.55;">{body}</div>'
        f'</div></div>'
    )


def _tile_roadmap(title: str, body: str) -> str:
    return (
        '<div class="rv-tile" style="min-height:140px;'
        'border-style:dashed;background:transparent;">'
        f'<div>'
        f'  <div class="rv-tile-eyebrow" style="color:var(--rv-ochre);">в работе</div>'
        f'  <div style="font-size:.98rem;font-weight:600;color:var(--rv-ink);'
        f'margin:.3rem 0 .5rem 0;line-height:1.25;text-transform:lowercase;">'
        f'{title.lower()}</div>'
        f'  <div style="color:var(--rv-ink-dim);font-size:.83rem;line-height:1.55;">{body}</div>'
        f'</div></div>'
    )


def _tile_tech(title: str, body: str) -> str:
    return (
        '<div class="rv-tile" style="min-height:130px;">'
        f'<div>'
        f'  <div style="font-size:.98rem;font-weight:600;color:var(--rv-ink);'
        f'margin-bottom:.4rem;line-height:1.25;text-transform:lowercase;">'
        f'{title.lower()}</div>'
        f'  <div style="color:var(--rv-ink-dim);font-size:.85rem;line-height:1.55;">{body}</div>'
        f'</div></div>'
    )


def _stat_card(label: str, value: str, sub: str) -> str:
    return (
        '<div class="rv-tile" style="min-height:130px;">'
        f'<div class="rv-tile-eyebrow">{label.lower()}</div>'
        f'<div style="font-size:1.75rem;font-weight:600;color:var(--rv-ink);'
        f'line-height:1.1;margin-top:.2rem;letter-spacing:-.015em;">{value}</div>'
        f'<div style="color:var(--rv-ink-mute);font-size:.78rem;'
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{sub}</div>'
        '</div>'
    )


def _grid(items: list[str], cols: int = 3) -> None:
    html = (
        f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);'
        'gap:12px;margin-bottom:14px;">' + "".join(items) + '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Вкладки
# ---------------------------------------------------------------------------

def _render_positioning() -> None:
    st.markdown(
        '<div class="rv-card">'
        '<div class="rv-h-eyebrow">о продукте</div>'
        '<div style="font-size:1.02rem;line-height:1.65;color:var(--rv-ink-dim);'
        'max-width:62ch;">'
        f'{data.POSITIONING}</div></div>',
        unsafe_allow_html=True,
    )


def _render_business_goals() -> None:
    section_h("·", "Бизнес-цели · что приложение закрывает")
    tiles = [_tile_goal(e, t, b) for e, t, b in data.BUSINESS_GOALS]
    _grid(tiles, cols=3)


def _render_compare_table() -> None:
    section_h("·", "Сводное сравнение возможностей")
    rows = [dict(zip(data.COMPARE_HEADERS, row)) for row in data.COMPARE_ROWS]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption(
        "Сравнение базируется на публичных тарифах и фичах конкурентов на момент "
        "написания. Если что-то поменялось — поправьте `src/about_data.py`."
    )


def _render_advantages() -> None:
    section_h("·", "Чем мы сильнее")
    tiles = [_tile_adv(t, b) for t, b in data.ADVANTAGES]
    _grid(tiles, cols=3)


def _render_roadmap() -> None:
    section_h("·", "Куда расти — план развития")
    tiles = [_tile_roadmap(t, b) for t, b in data.ROADMAP]
    cols = 3 if len(tiles) % 3 != 1 else 4
    _grid(tiles, cols=cols)
    st.caption("⚠️ Правило: реализованное СРАЗУ убирается отсюда (см. CLAUDE.md).")


def _render_dev_stats() -> None:
    section_h("·", "Статистика разработки")
    s = data.dev_stats()
    cards = [
        _stat_card("Версия", s["version"], f"sha {s['sha']}"),
        _stat_card("Коммитов", str(s["commits"]), "в ветке"),
        _stat_card("Рабочих дней", str(s["days"]), "уникальных дат коммитов"),
        _stat_card("Обновлено", s["last"], "последний коммит"),
    ]
    _grid(cards, cols=4)
    st.caption(
        "Данные из локального git. На Streamlit Cloud — из снапшота развёрнутого "
        "коммита (одно число дней = «деплой случился сегодня»)."
    )


def _render_visits() -> None:
    section_h("·", "Посещаемость дашборда")
    st.info(
        "🔜 Лог сессий ещё не подключён. План: лёгкий счётчик заходов "
        "(JSON в Drive) с сводкой «всего / активных за неделю». "
        "См. roadmap «Целевые КБЖУ + прогресс-бар» по приоритету."
    )


def _render_project_map() -> None:
    section_h("·", "Карта проекта")
    st.markdown(
        "- **app.py** — Streamlit-входная точка, страницы и навигация.\n"
        "- **src/file_loader.py** → **src/ocr.py** — извлечение текста из PDF/DOCX/фото.\n"
        "- **src/recipe_parser.py** — текст → структурированный `Recipe`.\n"
        "- **src/nutrition.py** — парсер ингредиентов + расчёт КБЖУ по `data/nutrition_ru.csv`.\n"
        "- **src/search.py** — поиск с лёгкой русской морфологией.\n"
        "- **src/categories.py** — категории-плитки из `data/categories.json`.\n"
        "- **src/pantry.py** — модель «Холодильника», парсинг пользовательского ввода.\n"
        "- **src/recipe_matcher.py** — подбор рецептов под холодильник + стартовый набор.\n"
        "- **src/meal_log.py** — модель «Дневник питания».\n"
        "- **src/google_drive.py** — синхронизация рецептов / дневника / холодильника в Drive.\n"
        "- **src/about_data.py / about_ui.py** — этот раздел."
    )
    st.caption(
        "🔜 Интерактивный граф зависимостей (Graphify/pydeps) — добавим, когда стек устаканится."
    )


def _render_tech_stack() -> None:
    section_h("·", "Технологический стек")
    tiles = [_tile_tech(t, b) for t, b in data.TECH_STACK]
    _grid(tiles, cols=3)


def _render_author() -> None:
    st.markdown(
        '<div style="padding:42px 22px;border-radius:var(--rv-radius);'
        'margin-top:18px;background:var(--rv-bg-card);'
        'border:1px solid var(--rv-border);text-align:center;">'
        '<div class="rv-h-eyebrow">автор продукта</div>'
        f'<div style="color:var(--rv-ink);font-size:1.9rem;font-weight:600;'
        f'margin-top:.4rem;letter-spacing:-.01em;">{data.AUTHOR}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Подробный гайд
# ---------------------------------------------------------------------------

def _guide_block(section: data.GuideSection) -> None:
    feats = "".join(f"<li style='margin-bottom:4px;'>{f}</li>" for f in section.features)
    steps_html = ""
    if section.steps:
        items = "".join(f"<li style='margin-bottom:4px;'>{s}</li>" for s in section.steps)
        steps_html = (
            '<div class="rv-h-eyebrow" style="margin-top:14px;">как пользоваться</div>'
            f'<ol style="color:var(--rv-ink-dim);font-size:.9rem;line-height:1.6;'
            f'margin:.4rem 0 .9rem 0;padding-left:22px;">{items}</ol>'
        )
    st.markdown(
        '<div class="rv-card" style="margin-bottom:14px;">'
        f'<div class="rv-h-eyebrow">{section.icon} {section.title.lower()}</div>'
        f'<div style="font-size:1.35rem;font-weight:600;color:var(--rv-ink);'
        f'margin:.2rem 0 .8rem 0;line-height:1.2;letter-spacing:-.01em;'
        f'text-transform:lowercase;">{section.title.lower()}</div>'
        f'<div style="color:var(--rv-ink-dim);font-size:.95rem;line-height:1.65;'
        f'margin-bottom:1rem;">{section.purpose}</div>'
        f'<div class="rv-h-eyebrow">что внутри</div>'
        f'<ul style="color:var(--rv-ink-dim);font-size:.9rem;line-height:1.6;'
        f'margin:.4rem 0 .9rem 0;padding-left:22px;">{feats}</ul>'
        f'{steps_html}'
        f'<div class="rv-h-eyebrow">как работает</div>'
        f'<div style="color:var(--rv-ink-dim);font-size:.9rem;line-height:1.65;'
        f'margin-top:.3rem;">{section.how}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_guide() -> None:
    section_h("·", "Подробный гайд по приложению")
    for section in data.GUIDE_SECTIONS:
        _guide_block(section)


# ---------------------------------------------------------------------------
# Главный вход
# ---------------------------------------------------------------------------

def render_about() -> None:
    if st.session_state.get("_about_guide"):
        page_header(
            eyebrow="о разработке · гайд",
            title="подробный гайд",
        )
        if st.button("← вернуться к разделу", key="guide_back"):
            st.session_state.pop("_about_guide", None)
            st.rerun()
        _render_guide()
        return

    page_header(
        eyebrow="о разработке",
        title="витрина продукта",
        lead="Что это, чем мы сильнее, куда растём и сколько в это вложено труда — "
             "сухая паспортная страница без маркетинга.",
    )

    if st.button("открыть подробный гайд по приложению",
                 type="primary", key="guide_open"):
        st.session_state["_about_guide"] = True
        st.rerun()

    tab_about, tab_compare, tab_stats, tab_tech = st.tabs([
        "о продукте",
        "сравнение возможностей",
        "статистика",
        "технологический стек",
    ])

    with tab_about:
        _render_positioning()
        hair()
        _render_business_goals()

    with tab_compare:
        _render_compare_table()
        hair()
        _render_advantages()
        hair()
        _render_roadmap()

    with tab_stats:
        _render_dev_stats()
        hair()
        _render_visits()
        hair()
        _render_project_map()

    with tab_tech:
        _render_tech_stack()

    hair()
    _render_author()
