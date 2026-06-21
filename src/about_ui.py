"""Рендер раздела «О разработке» (4 вкладки + автор + подробный гайд)."""
from __future__ import annotations

import streamlit as st

from . import about_data as data


_CSS_VARS = """
<style>
:root {
  --rv-bg-card: #FFFFFF;
  --rv-border: #E5E5E5;
  --rv-text: #3D405B;
  --rv-text-dim: #6F7681;
  --rv-brand: #E07A5F;
  --rv-money: #34D399;
  --rv-warn: #EAB308;
}
.rv-card-title { font-weight: 700; font-size: 1.05rem;
                 margin: 8px 0 6px 0; color: var(--rv-text); }
</style>
"""


def _hair() -> None:
    st.markdown(
        '<div style="border-top:1px solid var(--rv-border);'
        'margin:18px 0 14px 0;"></div>',
        unsafe_allow_html=True,
    )


def _h(title: str) -> None:
    st.markdown(f'<div class="rv-card-title">{title}</div>',
                unsafe_allow_html=True)


def _tile_goal(emoji: str, title: str, body: str) -> str:
    return (
        '<div style="background:var(--rv-bg-card);border:1px solid var(--rv-border);'
        'border-left:3px solid var(--rv-money);'
        'border-radius:14px;padding:16px 18px;min-height:150px;'
        'display:flex;flex-direction:column;">'
        f'<div style="color:var(--rv-text);font-size:0.98rem;font-weight:700;'
        f'margin-bottom:8px;line-height:1.3;">{emoji} {title}</div>'
        f'<div style="color:var(--rv-text-dim);font-size:0.84rem;line-height:1.55;'
        f'flex-grow:1;">{body}</div>'
        '</div>'
    )


def _tile_adv(title: str, body: str) -> str:
    return (
        '<div style="background:var(--rv-bg-card);border:1px solid var(--rv-border);'
        'border-radius:12px;padding:16px 18px;min-height:130px;'
        'display:flex;flex-direction:column;gap:6px;">'
        f'<div style="color:var(--rv-text);font-size:0.98rem;font-weight:700;">{title}</div>'
        f'<div style="color:var(--rv-text-dim);font-size:0.83rem;line-height:1.5;">{body}</div>'
        '</div>'
    )


def _tile_roadmap(title: str, body: str) -> str:
    return (
        '<div style="background:rgba(255,255,255,0.6);'
        'border:1px dashed var(--rv-border);'
        'border-radius:12px;padding:16px 18px;min-height:130px;'
        'display:flex;flex-direction:column;gap:6px;">'
        f'<div style="color:var(--rv-text);font-size:0.95rem;font-weight:700;">🔜 {title}</div>'
        f'<div style="color:var(--rv-text-dim);font-size:0.82rem;line-height:1.5;'
        f'flex-grow:1;">{body}</div>'
        '</div>'
    )


def _tile_tech(title: str, body: str) -> str:
    return (
        '<div style="background:var(--rv-bg-card);border:1px solid var(--rv-border);'
        'border-radius:12px;padding:16px 18px;min-height:120px;'
        'display:flex;flex-direction:column;gap:6px;">'
        f'<div style="color:var(--rv-text);font-size:0.98rem;font-weight:700;">{title}</div>'
        f'<div style="color:var(--rv-text-dim);font-size:0.83rem;line-height:1.5;">{body}</div>'
        '</div>'
    )


def _stat_card(label: str, value: str, sub: str) -> str:
    return (
        '<div style="background:var(--rv-bg-card);border:1px solid var(--rv-border);'
        'border-radius:12px;padding:16px 18px;height:110px;'
        'display:flex;flex-direction:column;justify-content:space-between;">'
        f'<div style="color:var(--rv-text-dim);font-size:0.78rem;">{label}</div>'
        f'<div style="color:var(--rv-text);font-size:1.6rem;font-weight:700;'
        f'line-height:1.1;">{value}</div>'
        f'<div style="color:var(--rv-text-dim);font-size:0.74rem;'
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
        '<div style="border:1px solid var(--rv-border);'
        'border-left:3px solid var(--rv-brand);'
        'border-radius:12px;background:rgba(224,122,95,0.05);'
        'padding:18px 22px;margin:6px 0;">'
        '<div style="color:var(--rv-text);font-size:1.05rem;font-weight:700;'
        'margin-bottom:10px;">О продукте</div>'
        f'<div style="color:var(--rv-text-dim);font-size:0.92rem;line-height:1.7;">'
        f'{data.POSITIONING}</div></div>',
        unsafe_allow_html=True,
    )


def _render_business_goals() -> None:
    _h("Бизнес-цели · что приложение закрывает")
    tiles = [_tile_goal(e, t, b) for e, t, b in data.BUSINESS_GOALS]
    _grid(tiles, cols=3)


def _render_compare_table() -> None:
    _h("Сводное сравнение возможностей")
    rows = [dict(zip(data.COMPARE_HEADERS, row)) for row in data.COMPARE_ROWS]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption(
        "Сравнение базируется на публичных тарифах и фичах конкурентов на момент "
        "написания. Если что-то поменялось — поправьте `src/about_data.py`."
    )


def _render_advantages() -> None:
    _h("Чем мы сильнее")
    tiles = [_tile_adv(t, b) for t, b in data.ADVANTAGES]
    _grid(tiles, cols=3)


def _render_roadmap() -> None:
    _h("Куда расти — план развития")
    tiles = [_tile_roadmap(t, b) for t, b in data.ROADMAP]
    cols = 3 if len(tiles) % 3 != 1 else 4
    _grid(tiles, cols=cols)
    st.caption("⚠️ Правило: реализованное СРАЗУ убирается отсюда (см. CLAUDE.md).")


def _render_dev_stats() -> None:
    _h("Статистика разработки")
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
    _h("Посещаемость дашборда")
    st.info(
        "🔜 Лог сессий ещё не подключён. План: лёгкий счётчик заходов "
        "(JSON в Drive) с сводкой «всего / активных за неделю». "
        "См. roadmap «Целевые КБЖУ + прогресс-бар» по приоритету."
    )


def _render_project_map() -> None:
    _h("Карта проекта")
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
    _h("Технологический стек")
    tiles = [_tile_tech(t, b) for t, b in data.TECH_STACK]
    _grid(tiles, cols=3)


def _render_author() -> None:
    st.markdown(
        '<div style="padding:22px;border-radius:14px;margin-top:18px;'
        'background:linear-gradient(90deg, rgba(224,122,95,0.14), rgba(224,122,95,0.02));'
        'border:1px solid #F2D6CB;text-align:center;">'
        '<div style="color:var(--rv-text-dim);font-size:0.78rem;'
        'text-transform:uppercase;letter-spacing:0.18em;">Автор продукта</div>'
        f'<div style="color:var(--rv-text);font-size:1.55rem;font-weight:800;'
        f'letter-spacing:0.04em;margin-top:8px;">{data.AUTHOR}</div>'
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
            '<div style="color:var(--rv-text);font-size:0.84rem;font-weight:700;'
            'margin:10px 0 4px 0;">Как пользоваться (по шагам):</div>'
            f'<ol style="color:var(--rv-text-dim);font-size:0.85rem;line-height:1.55;'
            f'margin:0 0 10px 0;padding-left:22px;">{items}</ol>'
        )
    st.markdown(
        '<div style="background:var(--rv-bg-card);border:1px solid var(--rv-border);'
        'border-radius:14px;padding:18px 22px;margin-bottom:14px;">'
        f'<div style="color:var(--rv-text);font-size:1.15rem;font-weight:800;'
        f'margin-bottom:10px;">{section.icon} {section.title}</div>'
        f'<div style="color:var(--rv-text-dim);font-size:0.88rem;line-height:1.6;'
        f'margin-bottom:10px;"><b style="color:var(--rv-text);">Зачем раздел:</b> '
        f'{section.purpose}</div>'
        f'<div style="color:var(--rv-text);font-size:0.84rem;font-weight:700;'
        f'margin-bottom:4px;">Что внутри / фишки:</div>'
        f'<ul style="color:var(--rv-text-dim);font-size:0.85rem;line-height:1.55;'
        f'margin:0 0 10px 0;padding-left:20px;">{feats}</ul>'
        f'{steps_html}'
        f'<div style="color:var(--rv-text-dim);font-size:0.85rem;line-height:1.6;">'
        f'<b style="color:var(--rv-text);">Как работает:</b> {section.how}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_guide() -> None:
    _h("Подробный гайд по приложению")
    for section in data.GUIDE_SECTIONS:
        _guide_block(section)


# ---------------------------------------------------------------------------
# Главный вход
# ---------------------------------------------------------------------------

def render_about() -> None:
    st.markdown(_CSS_VARS, unsafe_allow_html=True)
    st.title("ℹ️ О разработке")

    if st.session_state.get("_about_guide"):
        if st.button("← Вернуться к разделу «О разработке»", key="guide_back"):
            st.session_state.pop("_about_guide", None)
            st.rerun()
        _render_guide()
        return

    st.markdown(
        '<div style="color:var(--rv-text-dim);font-size:0.92rem;'
        'margin:-2px 0 12px 0;">'
        'Внутренняя витрина продукта: что это, чем сильнее, куда растём — '
        'и сколько в это вложено труда (без выдуманных метрик).'
        '</div>',
        unsafe_allow_html=True,
    )

    if st.button("📖 Открыть подробный гайд по приложению",
                 type="primary", key="guide_open"):
        st.session_state["_about_guide"] = True
        st.rerun()

    tab_about, tab_compare, tab_stats, tab_tech = st.tabs([
        "О продукте",
        "Сравнение возможностей",
        "Статистика",
        "Технологический стек",
    ])

    with tab_about:
        _render_positioning()
        _hair()
        _render_business_goals()

    with tab_compare:
        _render_compare_table()
        _hair()
        _render_advantages()
        _hair()
        _render_roadmap()

    with tab_stats:
        _render_dev_stats()
        _hair()
        _render_visits()
        _hair()
        _render_project_map()

    with tab_tech:
        _render_tech_stack()

    _hair()
    _render_author()
